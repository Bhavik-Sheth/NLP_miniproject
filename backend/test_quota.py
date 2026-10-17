import os
import tempfile
import unittest

import db


class FreeCommandQuotaTests(unittest.TestCase):
    def setUp(self):
        fd, self.path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        self.repo = db.Repo(db.connect(self.path), "P1")

    def tearDown(self):
        self.repo.db.close()
        os.unlink(self.path)

    def test_third_reservation_is_last_allowed_command(self):
        self.assertEqual(db.reserve_command(self.repo, "user_1", 3), (True, 1))
        self.assertEqual(db.reserve_command(self.repo, "user_1", 3), (True, 2))
        self.assertEqual(db.reserve_command(self.repo, "user_1", 3), (True, 3))
        self.assertEqual(db.reserve_command(self.repo, "user_1", 3), (False, 3))


if __name__ == "__main__":
    unittest.main()
