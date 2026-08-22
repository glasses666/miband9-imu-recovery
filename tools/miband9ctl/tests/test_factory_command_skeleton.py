import unittest

from factory_command_skeleton import (
    build_cta_app_list,
    build_cta_subscribe_behavior,
    build_cta_unsubscribe_behavior,
    build_factory_brightness,
    build_factory_dump,
    build_factory_media_dump,
    build_factory_mode,
)


class FactoryCommandSkeletonTests(unittest.TestCase):
    def test_factory_dump_matches_mi_fitness_e13_f2(self):
        self.assertEqual(bytes.fromhex("08 0d 10 02"), build_factory_dump())

    def test_factory_media_dump_matches_mi_fitness_e13_f4(self):
        self.assertEqual(bytes.fromhex("08 0d 10 04"), build_factory_media_dump())

    def test_factory_mode_serializes_iq9_field1_under_hns_field15(self):
        self.assertEqual(bytes.fromhex("08 0d 10 00 7a 02 08 02"), build_factory_mode(2))

    def test_factory_mode_rejects_unknown_modes(self):
        with self.assertRaises(ValueError):
            build_factory_mode(3)

    def test_factory_brightness_serializes_iq9_field6_under_hns_field15(self):
        self.assertEqual(bytes.fromhex("08 0d 10 05 7a 02 30 2a"), build_factory_brightness(42))

    def test_cta_app_list_matches_mi_fitness_e13_f9(self):
        self.assertEqual(bytes.fromhex("08 0d 10 09"), build_cta_app_list())

    def test_cta_subscribe_behavior_matches_mi_fitness_e13_f12(self):
        self.assertEqual(bytes.fromhex("08 0d 10 0c"), build_cta_subscribe_behavior())

    def test_cta_unsubscribe_behavior_matches_mi_fitness_e13_f13(self):
        self.assertEqual(bytes.fromhex("08 0d 10 0d"), build_cta_unsubscribe_behavior())


if __name__ == "__main__":
    unittest.main()
