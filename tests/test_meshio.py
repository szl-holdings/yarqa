# Copyright 2026 SZL Holdings
# SPDX-License-Identifier: Apache-2.0
"""Tests for yarqa.meshio — guarded .npz mesh I/O and SAMPLE synthetic data.

No OpenFOAM (or any CFD package) dependency is exercised or required.
"""
import pickle
import zipfile

import numpy as np
import pytest

from yarqa import Mesh, compartmentalize, mesh_fingerprint
from yarqa.cli import main
from yarqa.meshio import (
    load_npz_mesh,
    save_npz_mesh,
    sample_channel_mesh,
    try_load_openfoam,
)

# Set by _Payload.__reduce__ only if a loader unpickles an untrusted file.
_UNPICKLED = {"hit": False}


def _mark_unpickled():
    _UNPICKLED["hit"] = True
    return np.zeros((1, 2))


class _Payload:
    """Harmless stand-in for a malicious pickle: flips a flag when unpickled."""

    def __reduce__(self):
        return (_mark_unpickled, ())


def _write_npz_with_object_corners(path):
    corners = np.empty(3, dtype=object)
    for i in range(3):
        corners[i] = _Payload()
    np.savez(
        path,
        centers=np.array([[0.0, 0.0], [1.0, 0.0], [2.0, 0.0]]),
        velocities=np.tile([1.0, 0.0], (3, 1)),
        neighbors_flat=np.array([1, 0, 2, 1]),
        neighbors_offsets=np.array([0, 1, 3, 4]),
        corners=corners,
    )


def _assert_plain_numeric_npz(path):
    # Every array in the file must load without pickle support.
    with np.load(path, allow_pickle=False) as data:
        for key in data.files:
            assert data[key].dtype != object, key


def _grid(nx, ny):
    centers, neighbors = [], []
    idx = lambda i, j: i * ny + j
    for i in range(nx):
        for j in range(ny):
            centers.append([float(i), float(j)])
    centers = np.array(centers)
    for i in range(nx):
        for j in range(ny):
            nb = []
            if i > 0: nb.append(idx(i - 1, j))
            if i < nx - 1: nb.append(idx(i + 1, j))
            if j > 0: nb.append(idx(i, j - 1))
            if j < ny - 1: nb.append(idx(i, j + 1))
            neighbors.append(np.array(nb))
    vel = np.tile([1.0, 0.0], (len(centers), 1))
    return Mesh(centers, vel, neighbors)


def test_npz_roundtrip_preserves_mesh(tmp_path):
    mesh = _grid(6, 5)
    path = str(tmp_path / "mesh.npz")
    save_npz_mesh(path, mesh)
    loaded = load_npz_mesh(path)
    assert loaded.n == mesh.n and loaded.dim == mesh.dim
    assert np.allclose(loaded.centers, mesh.centers)
    assert np.allclose(loaded.velocities, mesh.velocities)
    # Fingerprints must match exactly -> a saved/loaded mesh is bit-identical.
    assert mesh_fingerprint(loaded) == mesh_fingerprint(mesh)


def test_npz_roundtrip_preserves_compartments(tmp_path):
    mesh = _grid(6, 6)
    path = str(tmp_path / "mesh.npz")
    save_npz_mesh(path, mesh)
    loaded = load_npz_mesh(path)
    assert np.array_equal(compartmentalize(mesh), compartmentalize(loaded))


def test_npz_with_object_neighbors_array(tmp_path):
    # A legacy hand-written npz using a single ragged 'neighbors' object array
    # needs pickle to load, so it is refused rather than unpickled.
    centers = np.array([[0.0, 0.0], [1.0, 0.0], [2.0, 0.0]])
    velocities = np.tile([1.0, 0.0], (3, 1))
    neighbors = np.array(
        [np.array([1]), np.array([0, 2]), np.array([1])], dtype=object
    )
    path = str(tmp_path / "obj.npz")
    np.savez(path, centers=centers, velocities=velocities, neighbors=neighbors)
    with pytest.raises(ValueError, match="legacy pickled npz refused"):
        load_npz_mesh(path)


def test_npz_with_rectangular_neighbors_array(tmp_path):
    # A plain numeric (N, K) 'neighbors' array is still accepted.
    centers = np.array([[0.0, 0.0], [1.0, 0.0], [2.0, 0.0]])
    velocities = np.tile([1.0, 0.0], (3, 1))
    neighbors = np.array([[1, 2], [0, 2], [0, 1]])
    path = str(tmp_path / "rect.npz")
    np.savez(path, centers=centers, velocities=velocities, neighbors=neighbors)
    loaded = load_npz_mesh(path)
    assert loaded.n == 3
    assert list(loaded.neighbors[1]) == [0, 2]


def test_npz_object_corners_payload_is_never_unpickled(tmp_path):
    path = str(tmp_path / "evil.npz")
    _write_npz_with_object_corners(path)
    _UNPICKLED["hit"] = False
    with pytest.raises(ValueError, match="legacy pickled npz refused"):
        load_npz_mesh(path)
    assert _UNPICKLED["hit"] is False
    # Same file through the CLI entry point.
    with pytest.raises(ValueError, match="legacy pickled npz refused"):
        main(["compartmentalize", path])
    assert _UNPICKLED["hit"] is False


def test_object_members_refused_without_npzfile_contains(tmp_path, monkeypatch):
    # NumPy 1.23/1.24 NpzFile has no __contains__, so `key in npz` falls back to
    # Mapping.__contains__ and reads the member. Emulate that here; the loader
    # must still name the refusal (it tests membership on npz.files).
    # (hasattr is always true through the Mapping base, so check the class dict.)
    if "__contains__" in vars(np.lib.npyio.NpzFile):
        monkeypatch.delattr(np.lib.npyio.NpzFile, "__contains__")
    path = str(tmp_path / "evil.npz")
    _write_npz_with_object_corners(path)
    _UNPICKLED["hit"] = False
    with pytest.raises(ValueError, match="legacy pickled npz refused"):
        load_npz_mesh(path)
    assert _UNPICKLED["hit"] is False
    obj = str(tmp_path / "obj.npz")
    np.savez(
        obj,
        centers=np.zeros((2, 2)),
        velocities=np.zeros((2, 2)),
        neighbors=np.array([np.array([1]), np.array([0])], dtype=object),
    )
    with pytest.raises(ValueError, match="legacy pickled npz refused"):
        load_npz_mesh(obj)
    good = str(tmp_path / "good.npz")
    save_npz_mesh(good, sample_channel_mesh(nx=3, ny=2))
    assert load_npz_mesh(good).n == 6


def test_oversized_header_is_not_reported_as_pickle(tmp_path):
    # NumPy's max_header_size refusal names the allow_pickle keyword but has
    # nothing to do with pickled data, so it must not be relabeled as a pickle
    # refusal.
    wide = np.zeros(2, dtype=[("x" * 20000, "<f8")])
    path = str(tmp_path / "wide.npz")
    np.savez(
        path,
        centers=wide,
        velocities=np.zeros((2, 2)),
        neighbors_flat=np.array([1, 0]),
        neighbors_offsets=np.array([0, 1, 2]),
    )
    with pytest.raises((ValueError, TypeError)) as info:
        load_npz_mesh(path)
    assert "refused" not in str(info.value)


def test_raw_pickle_file_is_never_unpickled(tmp_path):
    # np.load would unpickle a bare pickle stream if pickle were allowed.
    path = tmp_path / "mesh.npz"
    path.write_bytes(pickle.dumps(_Payload()))
    _UNPICKLED["hit"] = False
    with pytest.raises(ValueError, match="pickle loading refused"):
        load_npz_mesh(str(path))
    assert _UNPICKLED["hit"] is False


def test_object_npy_file_is_never_unpickled(tmp_path):
    # A single .npy holding an object array also needs pickle; it is refused.
    path = str(tmp_path / "mesh.npy")
    payload = np.empty(1, dtype=object)
    payload[0] = _Payload()
    np.save(path, payload)  # np.save pickles object arrays by default
    _UNPICKLED["hit"] = False
    with pytest.raises(ValueError, match="pickle loading refused"):
        load_npz_mesh(path)
    assert _UNPICKLED["hit"] is False


def test_numeric_npy_file_is_not_a_mesh(tmp_path):
    path = str(tmp_path / "centers.npy")
    np.save(path, np.zeros((3, 2)))
    with pytest.raises(ValueError, match="single .npy array"):
        load_npz_mesh(path)


def test_npz_member_without_npy_header_is_refused(tmp_path):
    # A zip member named like an array but holding raw pickle bytes comes back
    # from NpzFile as bytes; it must fail as ValueError and never be unpickled.
    path = tmp_path / "raw_member.npz"
    np.savez(
        path,
        centers=np.array([[0.0, 0.0], [1.0, 0.0]]),
        velocities=np.tile([1.0, 0.0], (2, 1)),
        neighbors_flat=np.array([1, 0]),
        neighbors_offsets=np.array([0, 1, 2]),
    )
    with zipfile.ZipFile(path, "a") as zf:
        zf.writestr("corners.npy", pickle.dumps(_Payload()))
    _UNPICKLED["hit"] = False
    with pytest.raises(ValueError, match="not a .npy array member"):
        load_npz_mesh(str(path))
    assert _UNPICKLED["hit"] is False


def test_npz_bad_offsets_raise(tmp_path):
    path = str(tmp_path / "badoff.npz")
    np.savez(
        path,
        centers=np.zeros((2, 2)),
        velocities=np.zeros((2, 2)),
        neighbors_flat=np.array([1, 0]),
        neighbors_offsets=np.array([0, 5, 2]),
    )
    with pytest.raises(ValueError, match="neighbors_offsets"):
        load_npz_mesh(path)


def test_npz_missing_fields_raises(tmp_path):
    path = str(tmp_path / "bad.npz")
    np.savez(path, centers=np.zeros((3, 2)))  # no velocities
    with pytest.raises(ValueError):
        load_npz_mesh(path)


def test_npz_missing_neighbors_raises(tmp_path):
    path = str(tmp_path / "bad2.npz")
    np.savez(path, centers=np.zeros((3, 2)), velocities=np.zeros((3, 2)))
    with pytest.raises(ValueError):
        load_npz_mesh(path)


def test_sample_mesh_is_deterministic_and_valid():
    a = sample_channel_mesh(nx=10, ny=6, seed=42)
    b = sample_channel_mesh(nx=10, ny=6, seed=42)
    assert a.n == 60 and a.dim == 2
    assert mesh_fingerprint(a) == mesh_fingerprint(b)
    # downstream velocity dominates (channel flows +x)
    assert np.mean(a.velocities[:, 0]) > 1.0
    labels = compartmentalize(a, align_threshold=0.2)
    assert np.all(labels >= 0)


def test_sample_mesh_corners_roundtrip(tmp_path):
    base = sample_channel_mesh(nx=4, ny=4)
    corners = [np.array([base.centers[i]]) for i in range(base.n)]
    mesh = Mesh(base.centers, base.velocities, base.neighbors, corners=corners)
    path = str(tmp_path / "corners.npz")
    save_npz_mesh(path, mesh)
    _assert_plain_numeric_npz(path)
    loaded = load_npz_mesh(path)
    assert loaded.corners is not None
    assert len(loaded.corners) == mesh.n
    assert mesh_fingerprint(loaded) == mesh_fingerprint(mesh)


def test_ragged_corners_roundtrip_is_csr_encoded(tmp_path):
    base = sample_channel_mesh(nx=3, ny=3)
    # Differing corner counts per cell (including an empty cloud).
    corners = [
        base.centers[i] + np.full((i % 4, base.dim), 0.25 * (i + 1))
        for i in range(base.n)
    ]
    mesh = Mesh(base.centers, base.velocities, base.neighbors, corners=corners)
    path = str(tmp_path / "ragged.npz")
    save_npz_mesh(path, mesh)
    _assert_plain_numeric_npz(path)
    with np.load(path, allow_pickle=False) as data:
        assert "corners" not in data.files
        assert data["corners_flat"].shape == (sum(len(c) for c in corners), 2)
        assert list(data["corners_offsets"]) == list(
            np.cumsum([0] + [len(c) for c in corners])
        )
    loaded = load_npz_mesh(path)
    for got, want in zip(loaded.corners, mesh.corners):
        assert got.shape == want.shape
        assert np.array_equal(got, want)
    assert mesh_fingerprint(loaded) == mesh_fingerprint(mesh)
    assert np.array_equal(compartmentalize(loaded), compartmentalize(mesh))


def test_save_rejects_malformed_corner_shape(tmp_path):
    base = sample_channel_mesh(nx=2, ny=2)
    corners = [np.zeros(3) for _ in range(base.n)]  # not (K, D)
    mesh = Mesh(base.centers, base.velocities, base.neighbors, corners=corners)
    with pytest.raises(ValueError, match=r"corners\[0\]"):
        save_npz_mesh(str(tmp_path / "bad.npz"), mesh)


def test_openfoam_hook_is_guarded():
    # Honest stub: must raise NotImplementedError, never a hard dependency.
    with pytest.raises(NotImplementedError):
        try_load_openfoam("/nonexistent/case")
