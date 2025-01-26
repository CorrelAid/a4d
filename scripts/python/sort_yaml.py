from argparse import ArgumentParser, FileType
from pathlib import Path

import yaml


def parse_args():
    parser = ArgumentParser(description='Sort YAML file')
    parser.add_argument('file', type=str, help='YAML file to sort')
    return parser.parse_args()


def sort_yaml():
    args = parse_args()
    yaml_file = Path(args.file).resolve()
    if not yaml_file.is_file():
        print(f'File not found: {yaml_file}')
        return
    
    with open(yaml_file, 'r') as f:
        data = yaml.safe_load(f)
    
    with open(yaml_file, 'w') as f:
        yaml.dump(data, f, sort_keys=True)
        print("YAML file sorted")
    
if __name__ == '__main__':
    sort_yaml()

