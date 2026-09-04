import asyncio
import unittest

from snake_lab.runtime_control import (
    SimulationCancelled,
    SimulationControl,
)


class SimulationControlTests(unittest.IsolatedAsyncioTestCase):
    async def test_pause_blocks_until_resume(self) -> None:
        control = SimulationControl()
        control.pause()

        checkpoint = asyncio.create_task(control.checkpoint())
        await asyncio.sleep(0)
        self.assertFalse(checkpoint.done())

        control.resume()
        await asyncio.wait_for(checkpoint, 0.1)

    async def test_cancel_interrupts_a_paused_checkpoint(self) -> None:
        control = SimulationControl()
        control.pause()
        checkpoint = asyncio.create_task(control.checkpoint())
        await asyncio.sleep(0)

        control.cancel()

        with self.assertRaises(SimulationCancelled):
            await asyncio.wait_for(checkpoint, 0.1)

    async def test_changing_delay_wakes_the_current_delay(self) -> None:
        control = SimulationControl()
        control.set_move_delay(100)
        checkpoint = asyncio.create_task(control.checkpoint())
        await asyncio.sleep(0.01)

        control.set_move_delay(0)

        await asyncio.wait_for(checkpoint, 0.1)

    async def test_delay_values_are_bounded_steps(self) -> None:
        control = SimulationControl()
        for value in (0, 20, 40, 60, 80, 100):
            with self.subTest(value=value):
                control.set_move_delay(value)
                self.assertEqual(control.move_delay_ms, value)

        for value in (-20, 10, 120, 1.0, True):
            with self.subTest(value=value), self.assertRaises(ValueError):
                control.set_move_delay(value)


if __name__ == "__main__":
    unittest.main()
