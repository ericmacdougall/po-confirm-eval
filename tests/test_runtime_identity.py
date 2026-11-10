import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))
from runtime_identity import verify_props, cache_identity, validate_endpoint


class RuntimeIdentity(unittest.TestCase):
    def test_only_owned_local_tunnel_endpoints_allowed(self):
        validate_endpoint('http://127.0.0.1:8081')
        for url in ('https://example.net', 'http://example.net', 'file:///models/local'):
            with self.assertRaises(ValueError):
                validate_endpoint(url)
    def setUp(self):
        self.meta = {"backend": {"build": 12242, "commit": "abc", "temperature": 0, "seed": 7,
                                  "max_completion_tokens": 320},
                     "models": {"small": {"files": {"small.gguf": "a" * 64}}}}
        self.props = {"build_info": "b12242-abc", "model_path": "/models/small.gguf",
                      "model_alias": "/models/small.gguf", "total_slots": 4,
                      "default_generation_settings": {"n_ctx": 4096}}

    def test_swapped_alias_or_build_refused(self):
        verify_props(self.props, "small", self.meta)
        for key, value in (("model_path", "/models/large.gguf"), ("model_alias", "large.gguf"),
                           ("build_info", "b999-different")):
            with self.subTest(key=key), self.assertRaises(ValueError):
                verify_props(dict(self.props, **{key: value}), "small", self.meta)
        with self.assertRaises(ValueError):
            verify_props(self.props, "forged-tag", self.meta)

    def test_cache_identity_changes_with_weights_build_and_decoding(self):
        import copy
        original = cache_identity(self.props, "small", self.meta)
        for kind in ("weights", "seed", "build"):
            meta = copy.deepcopy(self.meta)
            props = dict(self.props)
            if kind == "weights":
                meta["models"]["small"]["files"]["small.gguf"] = "b" * 64
            elif kind == "seed":
                meta["backend"]["seed"] = 8
            else:
                meta["backend"]["build"] = 999
                props["build_info"] = "b999-abc"
            self.assertNotEqual(original, cache_identity(props, "small", meta))


if __name__ == "__main__":
    unittest.main()
