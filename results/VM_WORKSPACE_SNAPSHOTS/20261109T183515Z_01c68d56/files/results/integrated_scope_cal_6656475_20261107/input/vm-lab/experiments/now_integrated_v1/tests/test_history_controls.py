import unittest
from nowexp.state import Config
from nowexp.history_controls import compare_foliations,compare_internal_slice,correction_and_selection


class HistoryControls(unittest.TestCase):
    def test_real_foliations_preserve_local_records(self):
        answer=compare_foliations(Config(forced_content=(1,1)),0)
        self.assertTrue(answer['all_equal'])
        self.assertGreater(len({tuple(x['event_order']) for x in answer['frames']}),1)

    def test_moving_worldlines_under_coordinate_change(self):
        self.assertTrue(compare_foliations(Config(forced_content=(1,1),receiver_velocity=.3),0)['all_equal'])

    def test_full_slices_include_pending_messages(self):
        for cut in (1,5,12,24,37):
            answer=compare_internal_slice(Config(forced_content=(1,1)),0,cut)
            self.assertTrue(answer['continuation_equal'])
            self.assertTrue(answer['full_final_state_equal'])

    def test_selection_keeps_denominator_and_no_future_input(self):
        answer=correction_and_selection(Config())
        self.assertFalse(answer['future_boundary_available_to_controller'])
        for arm in answer['arms']:
            self.assertAlmostEqual(arm['preparation_mass'],1)
            if arm['future_event_mass']==0:self.assertIsNone(arm['parent_given_future'])
            else:self.assertAlmostEqual(arm['parent_given_future'],arm['parent_and_future_mass']/arm['future_event_mass'])


if __name__=='__main__':unittest.main()
