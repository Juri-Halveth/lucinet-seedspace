# SPDX-License-Identifier: GPL-3.0-or-later
# Adapted from NOVA builder cb7c947 for a fictional adult Female_Peasant candidate.
"""Build the visual candidate from the three original, free Quaternius ZIPs.

Run with Blender --background --factory-startup --disable-autoexec --python
this-file -- --downloads <directory>. No downloaded Python or .blend is run.
Only data imports are used. Original ZIPs and the old humanoid stay unchanged.
"""
from pathlib import Path, PurePosixPath
import argparse
import hashlib
import json
import sys
import tempfile
import zipfile
import bpy
import bmesh

HERE = Path(__file__).resolve().parent


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def unpack(archive, destination):
    with zipfile.ZipFile(archive) as z:
        for member in z.infolist():
            name = PurePosixPath(member.filename)
            if member.is_dir():
                continue
            # Keep only glTF data and its images/buffers, and license/readme.
            if name.suffix.lower() not in {'.gltf', '.glb', '.bin', '.png', '.txt'}:
                continue
            path = destination.joinpath(*name.parts[1:]).resolve()
            if not path.is_relative_to(destination):
                raise ValueError('Archive path outside destination')
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(z.read(member))


def load(path):
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=str(path))
    objects = set(bpy.data.objects) - before
    # Blender's import helper creates a hidden bone-shape Icosphere.
    meshes = sorted((o for o in objects if o.type == 'MESH' and o.vertex_groups), key=lambda o: o.name)
    armature = next(o for o in objects if o.type == 'ARMATURE')
    return armature, meshes


def bind(mesh, target):
    world = mesh.matrix_world.copy()
    mesh.parent = target
    mesh.matrix_world = world
    for modifier in mesh.modifiers:
        if modifier.type == 'ARMATURE':
            modifier.object = target


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--downloads', type=Path, required=True)
    args = p.parse_args(sys.argv[sys.argv.index('--') + 1:])
    packages = {
        'base': ('Universal Base Characters[Standard].zip', 'fdbf1804c90dfc1ea03e992bff7da2dfd1a79318e13270a660180f9308455f40'),
        'outfit': ('Modular Character Outfits - Fantasy[Standard].zip', 'c3468b18871cc8c8f05ab14df7712baf22cb9f389cbd870babf130e595187f70'),
        'motion': ('Universal Animation Library[Standard].zip', 'cc73fc4e495b82958207316596317a3f40b9fa38065bde1027937452da537724'),
    }
    output = HERE / 'character-assets'
    output.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='nova-character-') as temp:
        roots = {}
        for label, (name, expected) in packages.items():
            archive = args.downloads / name
            if digest(archive) != expected:
                raise ValueError(f'Unreviewed archive: {name}')
            roots[label] = Path(temp, label).resolve()
            unpack(archive, roots[label])
            license_path = next(roots[label].glob('License*.txt'))
            license_text = license_path.read_text(encoding='utf-8')
            if 'CC0 1.0 Universal' not in license_text:
                raise ValueError(f'Unexpected license: {name}')
            # Preserve notice wording; normalize line endings/trailing space
            # so exported notice hashes also survive a Git LF checkout.
            notice = '\n'.join(line.rstrip() for line in license_text.splitlines()).rstrip() + '\n'
            (output / f'LICENSE-{label}.txt').write_bytes(notice.encode('utf-8'))

        # Repair one broken image URI in the vendor glTF, from its actual
        # sibling file. This does not synthesize or silently drop the normal.
        base_path = next(roots['base'].rglob('Superhero_Female_FullBody.gltf'))
        data = json.loads(base_path.read_text())
        for image in data['images']:
            if image.get('uri') == 'T_Eye_Normal_png.png':
                if not (base_path.parent / 'T_Eye_Normal.png').is_file():
                    raise ValueError('Eye normal source missing')
                image['uri'] = 'T_Eye_Normal.png'
        base_path.write_text(json.dumps(data), encoding='utf-8')

        bpy.ops.wm.read_factory_settings(use_empty=True)
        target, clothes = load(next(roots['outfit'].rglob('Outfits/Female_Peasant.gltf')))
        source, head_meshes = load(base_path)
        # These editions have identical named rest bones, not approximate
        # retargeting. Refuse a later revision that breaks this assumption.
        for bone in source.data.bones:
            other = target.data.bones.get(bone.name)
            if other is None or any(abs(a - b) > 1e-5 for ra, rb in zip(bone.matrix_local, other.matrix_local) for a, b in zip(ra, rb)):
                raise ValueError(f'Rest rig mismatch: {bone.name}')
        for mesh in head_meshes:
            if mesh.name.startswith('Superhero_Female'):
                # Clothing supplies the body. Keep only head+neck vertices;
                # hidden body surfaces must not intersect the outfit.
                # Weight masks are deformation data, not an anatomical cut.
                # The .999 head/neck threshold deleted blended nape vertices.
                # Retain the complete source head and a neck volume ending
                # under the outfit collar, including its original spine blend.
                def keep_vertex(v):
                    x, y, z = v.co
                    return z >= 1.535 or (z >= 1.445 and abs(x) <= .072 and abs(y) <= .115)
                remove = {v.index for v in mesh.data.vertices if not keep_vertex(v)}
                bm = bmesh.new()
                bm.from_mesh(mesh.data)
                bm.verts.ensure_lookup_table()
                bmesh.ops.delete(bm, geom=[bm.verts[i] for i in remove], context='VERTS')
                bm.to_mesh(mesh.data)
                bm.free()
                mesh.name = 'NOVA_Head_Neck'
            bind(mesh, target)

        hair_path = roots['base'] / 'Hairstyles/Rigged to Head Bone/glTF (Godot -Unreal)/Hair_Buns.gltf'
        hair_rig, hair = load(hair_path)
        for mesh in hair:
            bind(mesh, target)
        # Buns and hood occupy the same space. Use authored hair, without hood.
        for mesh in list(clothes):
            if 'Head_Hood' in mesh.name:
                clothes.remove(mesh)
                bpy.data.objects.remove(mesh, do_unlink=True)
        selected = [target, *clothes, *head_meshes, *hair]
        for obj in list(bpy.data.objects):
            if obj not in selected:
                bpy.data.objects.remove(obj, do_unlink=True)
        target.name = 'Fictional_Adult_Rig'
        # 1K texture ceiling keeps a browser preview light. Normal/ORM maps
        # and their color spaces are retained by the glTF exporter.
        for image in bpy.data.images:
            if image.size[0] > 1024 or image.size[1] > 1024:
                ratio = min(1024 / image.size[0], 1024 / image.size[1])
                image.scale(round(image.size[0] * ratio), round(image.size[1] * ratio))
        bpy.ops.object.select_all(action='DESELECT')
        for obj in selected:
            obj.select_set(True)
        bpy.context.view_layer.objects.active = target
        bpy.context.view_layer.update()
        bpy.ops.export_scene.gltf(filepath=str(output / 'fictional-adult.glb'), export_format='GLB', use_selection=True, export_animations=False, export_extras=False, export_image_format='AUTO')
        # Original unmodified animation asset, with 43 actual Standard clips.
        motion = next(roots['motion'].rglob('UAL1_Standard_RM.glb'))
        (output / 'motions.glb').write_bytes(motion.read_bytes())
        report = {
            'builder': 'build-character.py', 'blender': bpy.app.version_string,
            'rigRestEquality': '65_NAME_BOUND_REST_MATRICES_WITHIN_1E-5',
            'body': 'outfit body plus base head/neck only',
            'headCut': {'method': 'ANATOMICAL_REST_VOLUME_NOT_SKIN_WEIGHT_THRESHOLD', 'headMinZ': 1.535, 'neckMinZ': 1.445, 'neckHalfX': .072, 'neckHalfY': .115, 'originalBlendWeights': 'RETAINED'},
            'hair': 'Hair_Buns; hood omitted', 'textureCeiling': 1024,
            'sourceRepair': 'T_Eye_Normal_png.png URI -> existing T_Eye_Normal.png',
            'meshes': [{'name': o.name, 'vertices': len(o.data.vertices), 'triangles': sum(len(f.vertices) - 2 for f in o.data.polygons)} for o in selected if o.type == 'MESH'],
            'outputs': {n: {'bytes': (output/n).stat().st_size, 'sha256': digest(output/n)} for n in ['fictional-adult.glb', 'motions.glb']},
        }
        (output / 'BUILD.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
        print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
