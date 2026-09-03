import unittest
from contextlib import redirect_stdout
from io import StringIO

from snake_lab.simulator import Simulator


class FakeDevice:
    def __init__(self, device_type: str) -> None:
        self.type = device_type


class FakeTensor:
    def __add__(self, _value: int) -> "FakeTensor":
        return self

    def sum(self) -> "FakeTensor":
        return self

    def item(self) -> float:
        return 2.0


class FakeCuda:
    def __init__(self, available: bool) -> None:
        self.available = available
        self.synchronized = False

    def is_available(self) -> bool:
        return self.available

    def get_device_name(self, _device: FakeDevice) -> str:
        return "Test GPU"

    def synchronize(self, _device: FakeDevice) -> None:
        self.synchronized = True


class FakeTorch:
    def __init__(self, cuda_available: bool) -> None:
        self.cuda = FakeCuda(cuda_available)
        self.tensor_device: FakeDevice | None = None

    @staticmethod
    def device(device_type: str) -> FakeDevice:
        return FakeDevice(device_type)

    def ones(self, _size: int, device: FakeDevice) -> FakeTensor:
        self.tensor_device = device
        return FakeTensor()


class SimulatorTests(unittest.TestCase):
    def test_cpu_runtime(self) -> None:
        torch_module = FakeTorch(cuda_available=False)
        output = StringIO()

        with redirect_stdout(output):
            simulator = Simulator({"epochs": 1500}, torch_module)
            simulator.run()

        self.assertEqual(output.getvalue(), "Simulation running on CPU\n")
        self.assertEqual(simulator.runtime_description, "Simulation running on CPU")
        self.assertEqual(torch_module.tensor_device.type, "cpu")
        self.assertFalse(torch_module.cuda.synchronized)

    def test_gpu_runtime(self) -> None:
        torch_module = FakeTorch(cuda_available=True)
        output = StringIO()

        with redirect_stdout(output):
            simulator = Simulator({"epochs": 1500}, torch_module)
            simulator.run()

        self.assertEqual(
            output.getvalue(), "Simulation running on GPU (Test GPU)\n"
        )
        self.assertEqual(
            simulator.runtime_description,
            "Simulation running on GPU (Test GPU)",
        )
        self.assertEqual(torch_module.tensor_device.type, "cuda")
        self.assertTrue(torch_module.cuda.synchronized)


if __name__ == "__main__":
    unittest.main()
