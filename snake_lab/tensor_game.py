"""Device-resident Snake rules for one environment (leading batch size one).

The age grid encodes tail=1 through head=length, avoiding Python coordinates
and body scans in the move loop. CPU export is reserved for telemetry/results.
"""

import torch

from constants.DGame import DGameDef
from snake_lab.game import Direction, GameState, Outcome, Position, RewardConfig, StepResult


OUTCOMES = (
    Outcome.EMPTY, Outcome.FOOD, Outcome.WALL, Outcome.SNAKE,
    Outcome.MAX_MOVES, Outcome.BOARD_FILLED,
)


class TensorSnakeGame:
    def __init__(
        self, *, seed: int, episode_id: int, grid_size: tuple[int, int],
        initial_snake_length: int, max_moves_multiplier: int,
        rewards: RewardConfig, device: torch.device,
    ) -> None:
        self.seed = seed
        self.episode_id = episode_id
        self.width, self.height = grid_size
        self.capacity = self.width * self.height
        if not 0 < initial_snake_length <= self.width or initial_snake_length >= self.capacity:
            raise ValueError("initial snake must fit and leave a free cell")
        if max_moves_multiplier <= 0:
            raise ValueError("max_moves_multiplier must be positive")
        self.device = torch.device(device)
        self.rewards = rewards
        self.max_moves_multiplier = max_moves_multiplier
        self.generator = torch.Generator(device=self.device).manual_seed(seed)
        self.head = torch.tensor(
            [[max(self.width // 2, initial_snake_length - 1), self.height // 2]],
            device=self.device, dtype=torch.long,
        )
        self.direction = torch.tensor([[1, 0]], device=self.device)
        self.length = torch.full((1,), initial_snake_length, device=self.device, dtype=torch.long)
        self.ages = torch.zeros((1, self.capacity), device=self.device, dtype=torch.long)
        offsets = torch.arange(initial_snake_length, device=self.device)
        cells = (self.head[:, :1] - offsets) * self.height + self.head[:, 1:]
        self.ages.scatter_(1, cells, (initial_snake_length - offsets).unsqueeze(0))
        self.food = self._choose_food(self.ages)
        self.score = torch.zeros(1, device=self.device, dtype=torch.long)
        self.moves = torch.zeros_like(self.score)
        self.done = torch.zeros(1, device=self.device, dtype=torch.bool)
        self.outcome = torch.zeros_like(self.score)
        self.reward = torch.zeros(1, device=self.device)
        self.total_reward = torch.zeros(1, device=self.device)
        radius = DGameDef.OBSERVATION_RADIUS
        axis = torch.arange(-radius, radius + 1, device=self.device)
        y, x = torch.meshgrid(axis, axis, indexing="ij")
        self.local_x, self.local_y = x.flatten(), y.flatten()

    def _choose_food(self, ages: torch.Tensor) -> torch.Tensor:
        free = ages == 0
        count = free.sum(dim=1, keepdim=True)
        rank = (torch.rand((1, 1), generator=self.generator, device=self.device) * count).long()
        selected = (free & (free.long().cumsum(dim=1) == rank + 1)).long().argmax(dim=1)
        position = torch.stack((selected // self.height, selected % self.height), dim=1)
        return torch.where(count > 0, position, -torch.ones_like(position))

    def observe(self) -> torch.Tensor:
        forward = self.direction
        right = torch.stack((-forward[:, 1], forward[:, 0]), dim=1)
        positions = (
            self.head[:, None, :] + self.local_x[None, :, None] * right[:, None, :]
            - self.local_y[None, :, None] * forward[:, None, :]
        )
        x, y = positions[..., 0], positions[..., 1]
        inside = (x >= 0) & (x < self.width) & (y >= 0) & (y < self.height)
        indices = (x * self.height + y).clamp(0, self.capacity - 1)
        occupied = self.ages.gather(1, indices) > 0
        food = (positions == self.food[:, None, :]).all(dim=2)
        values = torch.where(food, 1.0, 0.0)
        values = torch.where(occupied, 0.5, values)
        values = torch.where(inside, values, -0.5)
        values[:, self.local_x.numel() // 2] = 0
        relative = self.food - self.head
        signs = torch.stack(
            ((relative * right).sum(dim=1), -(relative * forward).sum(dim=1)), dim=1,
        ).sign().float()
        signs = torch.where((self.food >= 0).all(dim=1, keepdim=True), signs, 0.0)
        return torch.cat((values, signs), dim=1)

    def step(self, action: torch.Tensor) -> torch.Tensor:
        """Advance without reading an action or game state back to the host."""
        action = action.reshape(1)
        left = torch.stack((self.direction[:, 1], -self.direction[:, 0]), dim=1)
        right = -left
        direction = torch.where((action == 0)[:, None], left, self.direction)
        direction = torch.where((action == 2)[:, None], right, direction)
        head = self.head + direction
        moves = self.moves + 1
        exhausted = moves > self.max_moves_multiplier * self.length
        wall = (head[:, 0] < 0) | (head[:, 0] >= self.width) | (head[:, 1] < 0) | (head[:, 1] >= self.height)
        ate = (head == self.food).all(dim=1)
        index = (head[:, 0] * self.height + head[:, 1]).clamp(0, self.capacity - 1)
        age = self.ages.gather(1, index[:, None]).squeeze(1)
        collision = age > torch.where(ate, 0, 1)
        valid = ~(exhausted | wall | collision | self.done)
        length = self.length + ate.long()
        ages = (self.ages - (~ate).long()[:, None]).clamp_min(0)
        ages.scatter_(1, index[:, None], length[:, None])
        old_distance = (self.head - self.food).abs().sum(dim=1)
        new_distance = (head - self.food).abs().sum(dim=1)
        reward = torch.where(
            new_distance < old_distance,
            self.rewards.empty + self.rewards.closer_to_food,
            self.rewards.empty + self.rewards.further_from_food,
        )
        reward = torch.where(ate, self.rewards.food, reward)
        filled = ate & (length == self.capacity)
        outcome = torch.where(ate, 1, 0)
        outcome = torch.where(filled, 5, outcome)
        # Match the reference rule precedence: max moves, wall, then body.
        for condition, code, value in (
            (collision, 3, self.rewards.snake),
            (wall, 2, self.rewards.wall),
            (exhausted, 4, self.rewards.max_moves),
        ):
            outcome = torch.where(condition, code, outcome)
            reward = torch.where(condition, value, reward)
        self.ages = torch.where(valid[:, None], ages, self.ages)
        candidate_food = self._choose_food(self.ages)
        self.food = torch.where((valid & ate)[:, None], candidate_food, self.food)
        self.head = torch.where(valid[:, None], head, self.head)
        self.direction = torch.where(valid[:, None], direction, self.direction)
        self.length = torch.where(valid, length, self.length)
        self.score += (valid & ate).long()
        self.reward = torch.where(self.done, 0.0, reward)
        self.total_reward += self.reward
        self.outcome = torch.where(self.done, self.outcome, outcome)
        self.moves = torch.where(self.done, self.moves, moves)
        self.done |= exhausted | wall | collision | filled
        return self.observe()

    def export_step(self) -> StepResult:
        """Materialize a CPU snapshot only when a viewer needs it."""
        ages = self.ages[0].detach().cpu()
        ordered = ages.argsort(descending=True)[:int(self.length.item())].tolist()
        coordinates = [Position(cell // self.height, cell % self.height) for cell in ordered]
        food = self.food[0].tolist()
        direction = self.direction[0].tolist()
        state = GameState(
            snake_head=coordinates[0], snake_body=tuple(coordinates[1:]),
            direction=Direction(*direction),
            food_position=Position(*food) if food[0] >= 0 else None,
            score=int(self.score.item()), move_count=int(self.moves.item()),
            grid_size=(self.width, self.height), seed=self.seed, episode_id=self.episode_id,
        )
        return StepResult(
            new_state=state, observation=tuple(self.observe()[0].tolist()),
            reward=float(self.reward.item()),
            outcome=OUTCOMES[int(self.outcome.item())], done=bool(self.done.item()),
        )
