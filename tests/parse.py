#!/usr/bin/env python3

import string


def parse_simple(path):
    with open(path) as f:
        lines = [line for line in f.readlines() if line]
        res = {}
        for line in lines:
            head, *tail = line.split()
            res[head] = tail
        print(res)


def parse_target(path):
    with open(path) as f:
        lines = [line for line in f.readlines() if line]
        res = {'header':[], 'core':[], 'static':[], 'shared':[], 'disabled': []}
        core, static, shared, disabled = 0,0,0,0
        lines = [line.strip() for line in lines if line]
        length = len(lines)
        for i, line in enumerate(lines):
            line = line.strip()
            if any(line.startswith(p) for p in string.ascii_uppercase):
                # print(i, line)
                res['header'].append(line)

        # from IPython import embed; embed()
        lines = lines[i:length-i]
        for i, line in enumerate(lines):
            print(i, line)

        # for line in lines:
        #     line = line.strip()
        #     if line.startswith("# core"):
        #         in_section = True
        #         continue
        #     if in_section:
        #         res['core'].append(line)

        #     if any(line.startswith(p) for p in ["*static*", "*shared*", "*disabled*"]):
        #         in_section = False

        #     # head, *tail = line.split()
        #     # res[head] = tail
        # print(res)


if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser()
    opt = parser.add_argument

    opt("target", help="target file to parse")

    args = parser.parse_args()
    parse_simple(args.target)
