import asyncio
from collections import Counter
import json
from pathlib import Path
import sys
import time
import torch

ROOT = Path('/opt/dev/snake-lab')
sys.path.insert(0, str(ROOT))
from snakelab.server.Configuration import simulation_config_template
from snakelab.server.Simulator import Simulator

out = ROOT / 'artifacts/transformer-epsilon-nice-500-baseline'
config = simulation_config_template().resolve(json.loads((ROOT / 'examples/transformer-epsilon-nice.json').read_text()))
(out / 'config.json').write_text(json.dumps(config, indent=2) + '\n')
started = time.monotonic()
updates = []

def record(result, state):
    row = result.to_dict()
    updates.append(row)
    with (out / 'episodes.jsonl').open('a') as stream:
        stream.write(json.dumps(row) + '\n')
    if result.episode % 25 == 0 or result.score >= 5:
        recent = updates[-25:]
        print(json.dumps({'epoch': result.episode, 'high_score': state.high_score, 'score': result.score, 'mean_last_25': sum(r['score'] for r in recent) / len(recent), 'steps': state.total_steps, 'epsilon': result.epsilon, 'loss': result.loss, 'elapsed_s': round(time.monotonic() - started, 1)}), flush=True)

async def main():
    simulator = Simulator(config, log_file=str(out / 'run.log'), on_episode=record)
    torch.set_num_threads(1)
    state = await simulator.run()
    summary = state.summary() | {
        'elapsed_s': time.monotonic() - started,
        'score_counts': dict(Counter(row['score'] for row in updates)),
        'outcome_counts': dict(Counter(row['outcome'] for row in updates)),
        'training_updates': sum(row['loss'] is not None for row in updates),
        'torch_version': torch.__version__,
        'torch_threads': torch.get_num_threads(),
        'epsilon_nice_stats': simulator.epsilon_nice.get_stats(),
    }
    (out / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')
    torch.save({'model': simulator.model.state_dict(), 'config': config}, out / 'model.pt')
    (out / 'highscore-frames.json').write_text(json.dumps([frame.to_dict() for frame in state.high_score_frames]))
    print('FINAL ' + json.dumps(summary), flush=True)

asyncio.run(main())
