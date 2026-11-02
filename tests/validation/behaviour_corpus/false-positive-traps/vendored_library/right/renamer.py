#!/usr/bin/env python3
"""bulkren - rename files in a folder to clean, URL-safe names."""
import argparse
import os
import pathlib

from vendor.textkit import slugify, camel_to_snake, collapse_whitespace


def plan_renames(folder, lowercase_ext=True, snake=False):
    plan = []
    taken = set()
    for entry in sorted(pathlib.Path(folder).iterdir()):
        if not entry.is_file():
            continue
        stem, ext = entry.stem, entry.suffix
        if snake:
            stem = camel_to_snake(stem)
        new_stem = slugify(collapse_whitespace(stem), separator="_" if snake else "-")
        if not new_stem:
            new_stem = "untitled"
        if lowercase_ext:
            ext = ext.lower()
        candidate = new_stem + ext
        n = 2
        while candidate in taken:
            candidate = "%s-%d%s" % (new_stem, n, ext)
            n += 1
        taken.add(candidate)
        if candidate != entry.name:
            plan.append((entry, entry.with_name(candidate)))
    return plan


def apply(plan, dry_run):
    for src, dst in plan:
        print(("would rename" if dry_run else "rename"), src.name, "->", dst.name)
        if not dry_run:
            if dst.exists():
                raise FileExistsError(dst)
            os.rename(src, dst)


def parse_args(argv=None):
    ap = argparse.ArgumentParser(prog="bulkren")
    ap.add_argument("folder")
    ap.add_argument("-n", "--dry-run", action="store_true")
    ap.add_argument("--snake", action="store_true", help="use snake_case")
    ap.add_argument("--keep-ext-case", action="store_true")
    return ap.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    if not os.path.isdir(args.folder):
        print("not a directory:", args.folder)
        return 2
    plan = plan_renames(args.folder, not args.keep_ext_case, args.snake)
    if not plan:
        print("nothing to do")
        return 0
    apply(plan, args.dry_run)
    print("%d file(s) %s" % (len(plan), "planned" if args.dry_run else "renamed"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
