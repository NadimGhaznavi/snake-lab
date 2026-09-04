import asyncio
import json
import unittest

from snake_lab.game import Outcome
from snake_lab.telemetry import BoardSnapshot, FrameTelemetry
from snake_lab.telemetry_zmq import TelemetryPublisher


class FakeSocket:
    def __init__(self) -> None:
        self.sent = []

    def setsockopt(self, _option: int, _value: int) -> None:
        pass

    def bind(self, _endpoint: str) -> None:
        pass

    async def send_multipart(self, frames: list[bytes]) -> None:
        self.sent.append(frames)

    def close(self) -> None:
        pass


class FakeContext:
    def __init__(self) -> None:
        self.socket_instance = FakeSocket()

    def socket(self, _socket_type: int) -> FakeSocket:
        return self.socket_instance


def frame(step: int) -> FrameTelemetry:
    return FrameTelemetry(
        episode=1,
        step=step,
        action=1,
        reward=0.0,
        done=False,
        outcome=Outcome.EMPTY,
        board=BoardSnapshot(
            width=4,
            height=1,
            snake_head=(step % 4, 0),
            snake_body=(),
            food=(3, 0),
            direction=(1, 0),
            score=0,
        ),
    )


class TelemetryPublisherTests(unittest.IsolatedAsyncioTestCase):
    async def test_diagnostic_mode_preserves_every_offered_frame(self) -> None:
        context = FakeContext()
        publisher = TelemetryPublisher(
            context=context,
            address="127.0.0.1",
            port=41971,
            frame_rate=15,
        )
        publisher.start()

        for step in (1, 2, 3):
            publisher.offer_frame("run-1", frame(step), preserve=True)
        await self._wait_for_messages(context.socket_instance, 3)
        await publisher.close()

        self.assertEqual(
            [
                json.loads(frames[1].decode("utf-8"))["payload"]["step"]
                for frames in context.socket_instance.sent
            ],
            [1, 2, 3],
        )

    async def test_full_speed_mode_keeps_only_the_latest_frame(self) -> None:
        context = FakeContext()
        publisher = TelemetryPublisher(
            context=context,
            address="127.0.0.1",
            port=41971,
            frame_rate=15,
        )
        publisher.start()

        for step in (1, 2, 3):
            publisher.offer_frame("run-1", frame(step))
        await self._wait_for_messages(context.socket_instance, 1)
        await publisher.close()

        payload = json.loads(
            context.socket_instance.sent[0][1].decode("utf-8")
        )["payload"]
        self.assertEqual(payload["step"], 3)

    @staticmethod
    async def _wait_for_messages(socket: FakeSocket, count: int) -> None:
        for _attempt in range(100):
            if len(socket.sent) >= count:
                return
            await asyncio.sleep(0.001)
        raise AssertionError("Telemetry publisher did not send in time")


if __name__ == "__main__":
    unittest.main()
