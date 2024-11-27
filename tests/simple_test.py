import unittest

from loguru import logger


class ISimpleTest(unittest.TestCase):
    def setUp(self):
        self.message = f"I am simple test {self.__class__.__name__}"

    def test_hello(self):
        logger.info(f"Message {self.message}")


if __name__ == "__main__":
    unittest.main()
