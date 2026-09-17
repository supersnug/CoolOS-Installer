"""CPU selection and Pacman priority are tested without changing the host."""
import importlib.util
import pathlib
import unittest

PATH = pathlib.Path(__file__).resolve().parents[1] / "src/scripts/configure-coolos-repositories.py"
SPEC = importlib.util.spec_from_file_location("coolos_repositories", PATH)
REPOS = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(REPOS)


def loader(level):
    return "\n".join(f"x86-64-v{n} " + ("(supported, searched)" if n <= level else "")
                     for n in (2, 3, 4))


def cpu(vendor="AuthenticAMD", family=25, model=97, flags=None):
    flags = REPOS.ZEN4_FLAGS if flags is None else flags
    return f"vendor_id : {vendor}\ncpu family : {family}\nmodel : {model}\nflags : {' '.join(sorted(flags))}\n"


class RepositoryTests(unittest.TestCase):
    def test_baseline_and_v3(self):
        self.assertEqual(REPOS.select_target(loader(2), cpu()), "x86-64")
        self.assertEqual(REPOS.select_target(loader(3), cpu(vendor="GenuineIntel")), "x86-64-v3")

    def test_zen_requires_all_features(self):
        self.assertEqual(REPOS.select_target(loader(4), cpu()), "znver4")
        self.assertEqual(REPOS.select_target(loader(4), cpu(family=26)), "znver4")
        for flag in REPOS.ZEN4_FLAGS:
            with self.subTest(flag=flag):
                self.assertEqual(REPOS.select_target(loader(4), cpu(flags=REPOS.ZEN4_FLAGS - {flag})), "x86-64-v4")

    def test_unknown_or_mixed_cpus(self):
        for info in ("", cpu(vendor="GenuineIntel"), cpu(model=1), cpu(family=27),
                     cpu() + "\n" + cpu(flags=set())):
            self.assertEqual(REPOS.select_target(loader(4), info), "x86-64-v4")

    def test_order_fallback_and_idempotence(self):
        original = "[options]\nArchitecture = auto\nSigLevel = Required DatabaseOptional\n\n[coolos]\nServer = old\n\n[cachyos]\nInclude = /etc/pacman.d/cachyos-mirrorlist\n\n[core]\nInclude = /etc/pacman.d/mirrorlist\n"
        for target, tiers in (("x86-64", ["coolos"]), ("x86-64-v3", ["coolos-v3", "coolos"]),
                              ("x86-64-v4", ["coolos-v4", "coolos-v3", "coolos"]),
                              ("znver4", list(REPOS.REPOSITORIES))):
            with self.subTest(target=target):
                output = REPOS.configure(original, target)
                self.assertEqual(output, REPOS.configure(output, target))
                actual = [line[1:-1] for line in output.splitlines() if line.startswith("[coolos")]
                self.assertEqual(actual, tiers)
                self.assertEqual(output.count("Server = https://coolos-repo.sarulean.com/$repo/$arch"), len(tiers))
                self.assertLess(output.index("[coolos]"), output.index("[cachyos]"))
                self.assertIn("SigLevel = Required DatabaseOptional", output)
                self.assertIn("[core]\nInclude = /etc/pacman.d/mirrorlist", output)

    def test_downgrade_removes_incompatible_tiers(self):
        original = REPOS.configure("[options]\n[core]\nServer = core\n", "znver4")
        output = REPOS.configure(original, "x86-64-v3")
        self.assertNotIn("[coolos-znver4]", output)
        self.assertNotIn("[coolos-v4]", output)


if __name__ == "__main__":
    unittest.main()
