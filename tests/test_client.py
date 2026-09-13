import unittest
from unittest.mock import patch, MagicMock
from blofin.client import Client
from blofin.exceptions import BlofinAPIException

class TestClient(unittest.TestCase):
    def setUp(self):
        self.apiKey = "test_api_key"
        self.apiSecret = "test_api_secret"
        self.client = Client(apiKey=self.apiKey, apiSecret=self.apiSecret)

    def test_init(self):
        """Test client initialization"""
        self.assertEqual(self.client.API_KEY, self.apiKey)
        self.assertEqual(self.client.API_SECRET.decode('utf-8'), self.apiSecret)

    def test_nonces_differ_within_one_millisecond(self):
        """The nonce was the millisecond clock, so clients signing with one key in the
        same millisecond sent the same one and BloFin rejected an order 152407
        "Repeated nonce" (2026-09-13). With the clock frozen, two nonces from one
        client and one from a second client must all differ, and each must be
        signed: the same request with another nonce has another signature."""
        other = Client(apiKey=self.apiKey, apiSecret=self.apiSecret)
        with patch("blofin.client.time.time", return_value=1789335574.914):
            nonces = [self.client._get_nonce(), self.client._get_nonce(), other._get_nonce()]
        self.assertEqual(len(set(nonces)), 3)
        signatures = {self.client._sign_request("1789335574914", "POST", "/api/v1/trade/order", {}, n)
                      for n in nonces}
        self.assertEqual(len(signatures), 3)

if __name__ == '__main__':
    unittest.main()
