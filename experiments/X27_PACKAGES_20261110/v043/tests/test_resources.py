import unittest

from x27.engine import apply_resource_operation
from x27.model import ResourceOperation, ResourceVector


class ResourceEngineTests(unittest.TestCase):
    def test_inflow_overflow_is_recorded(self):
        result = apply_resource_operation(
            ResourceVector(3, 2, 0, 0),
            ResourceOperation("SATURATION", inflow=ResourceVector(1, 1, 0, 0)),
        )
        self.assertFalse(result.exhausted)
        self.assertEqual(result.resources.as_tuple(), (3, 3, 0, 0))
        self.assertEqual(result.spill_inflow.as_tuple(), (1, 0, 0, 0))

    def test_cost_is_atomic_and_no_byproduct_on_exhaustion(self):
        start = ResourceVector(0, 1, 0, 0)
        result = apply_resource_operation(
            start,
            ResourceOperation(
                "TASK",
                cost=ResourceVector(1, 0, 0, 0),
                byproduct=ResourceVector(0, 0, 1, 0),
            ),
        )
        self.assertTrue(result.exhausted)
        self.assertEqual(result.resources, start)
        self.assertEqual(result.spill_byproduct.as_tuple(), (0, 0, 0, 0))
        self.assertNotIn("BYPRODUCT_ADDED", result.events)

    def test_byproduct_overflow_is_recorded(self):
        result = apply_resource_operation(
            ResourceVector(1, 1, 3, 0),
            ResourceOperation("REPAIR", cost=ResourceVector(1, 1, 0, 0), byproduct=ResourceVector(0, 0, 1, 1)),
        )
        self.assertFalse(result.exhausted)
        self.assertEqual(result.resources.as_tuple(), (0, 0, 3, 1))
        self.assertEqual(result.spill_byproduct.as_tuple(), (0, 0, 1, 0))


if __name__ == "__main__":
    unittest.main()
