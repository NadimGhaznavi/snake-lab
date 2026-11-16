"""Reproduce the smaller Transformer example using the server's CPU runtime.

Run from the repository root: venv/bin/python artifacts/transformer-epsilon-500-small/run.py
"""

import asyncio
from collections import Counter
import json
from pathlib import Path
import sys
import time

import torch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from snakelab.server.Configuration import simulation_config_template
from snakelab.server.Simulator import Simulator


async def main():
    out = Path(__file__).resolve().parent
    config = simulation_config_template().resolve(json.loads(
        (ROOT / 'examples/transformer-epsilon.json').read_text()
    ))
    (out / 'config.json').write_text(json.dumps(config, indent=2) + '\n')
    started = time.monotonic()
    with (out / 'episodes.jsonl').open('w') as episodes:
        def record(result, state):
            episodes.write(json.dumps(result.to_dict()) + '\n')
            episodes.flush()
            if result.episode % 25 == 0:
                recent = state.episodes[-25:]
                print(json.dumps({
                    'episode': result.episode, 'high_score': state.high_score,
                    'score': result.score,
                    'mean_last_25': sum(row.score for row in recent) / len(recent),
                    'elapsed_s': round(time.monotonic() - started, 1),
                }), flush=True)

        simulator = Simulator(config, log_file=str(out / 'run.log'), on_episode=record)
        state = await simulator.run()

    rows = state.episodes
    summary = state.summary() | {
        'elapsed_s': time.monotonic() - started,
        'mean_score': sum(row.score for row in rows) / len(rows),
        'mean_last_100': sum(row.score for row in rows[-100:]) / len(rows[-100:]),
        'first_score_10_episode': next((row.episode for row in rows if row.score >= 10), None),
        'score_10_episodes': sum(row.score >= 10 for row in rows),
        'score_counts': dict(Counter(row.score for row in rows)),
        'outcome_counts': dict(Counter(row.outcome.value for row in rows)),
        'training_updates': sum(row.loss is not None for row in rows),
        'torch_version': torch.__version__,
        'torch_threads': torch.get_num_threads(),
    }
    (out / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')
    print('FINAL ' + json.dumps(summary), flush=True)


if __name__ == '__main__':
    asyncio.run(main())
