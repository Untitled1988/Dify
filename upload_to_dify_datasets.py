import os
import sys
import json
import argparse
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import requests


def load_api_base_from_config(config_path: Path) -> Optional[str]:
    """Try to load API base URL from difyConfig.txt if present."""
    try:
        if config_path.exists():
            with open(config_path, 'r', encoding='utf-8') as f:
                cfg = json.load(f)
                api_base = (
                    cfg.get('DIFY', {}).get('API_BASE_URL')
                    or cfg.get('api_base')
                )
                return api_base
    except Exception:
        pass
    return None


class DifyDatasetClient:
    """Minimal client for Dify Dataset APIs."""

    def __init__(self, api_base: str, dataset_api_key: str, timeout: int = 60):
        self.api_base = api_base.rstrip('/')
        self.token = dataset_api_key
        self.session = requests.Session()
        self.session.headers.update({
            'Authorization': f'Bearer {self.token}'
        })
        self.timeout = timeout

    def list_datasets(self, page: int = 1, page_size: int = 100) -> Tuple[List[Dict], bool]:
        """List datasets. Returns (datasets, has_more)."""
        url = f"{self.api_base}/datasets"
        params = {"page": page, "page_size": page_size}
        resp = self.session.get(url, params=params, timeout=self.timeout)
        resp.raise_for_status()
        data = resp.json()
        # Compatible with possible shapes: {data: [...], has_more: bool} or pagination meta
        datasets = data.get('data') if isinstance(data, dict) else data
        if datasets is None:
            datasets = data.get('items', [])
        total = data.get('total', None)
        has_more = False
        if total is not None:
            has_more = page * page_size < int(total)
        else:
            # Fallback by next/page info
            has_more = bool(data.get('has_more'))
        return datasets or [], has_more

    def get_all_datasets(self) -> List[Dict]:
        page = 1
        all_items: List[Dict] = []
        while True:
            items, has_more = self.list_datasets(page=page)
            all_items.extend(items)
            if not has_more or not items:
                break
            page += 1
        return all_items

    def upload_document_by_file(self,
                                 dataset_id: str,
                                 file_path: Path,
                                 parent_separator: str,
                                 child_separator: str,
                                 parent_max_chars: int,
                                 child_max_chars: int,
                                 indexing_technique: str = 'high_quality') -> Dict:
        """Upload a local file into a dataset with custom parent-child segmentation rules."""
        url = f"{self.api_base}/datasets/{dataset_id}/document/create-by-file"

        # Construct process rules with correct hierarchical segmentation for Dify API
        process_rule = {
            "mode": "hierarchical",
            "rules": {
                "pre_processing_rules": [
                    {"id": "remove_extra_spaces", "enabled": False},
                    {"id": "remove_urls_emails", "enabled": False}
                ],
                # Main segmentation rules
                "segmentation": {
                    "separator": parent_separator,
                    "max_tokens": parent_max_chars
                },
                # Parent mode for recall
                "parent_mode": "paragraph",
                # Sub-chunk segmentation rules
                "subchunk_segmentation": {
                    "separator": child_separator,
                    "max_tokens": child_max_chars
                }
            }
        }

        meta = {
            "name": file_path.name,
            "indexing_technique": indexing_technique,
            "doc_form": "hierarchical_model",
            "process_rule": process_rule
        }

        files = {
            'file': (file_path.name, open(file_path, 'rb'), 'application/octet-stream')
        }
        data = {
            'data': json.dumps(meta, ensure_ascii=False)
        }
        resp = self.session.post(url, files=files, data=data, timeout=self.timeout)
        resp.raise_for_status()
        return resp.json()


def build_dataset_name_map() -> Dict[str, str]:
    """Map filename prefixes to actual dataset names."""
    # Prefix -> Dataset Name
    return {
        'Other': 'Other',
        '业务知识': '业务知识',
        '运维手册': '运维手册/SOP/KBA',
        'SOP': '运维手册/SOP/KBA',
        'KBA': '运维手册/SOP/KBA'
    }


def resolve_dataset_name_by_prefix(filename: str, name_map: Dict[str, str]) -> Optional[str]:
    prefix = Path(filename).stem.split('_', 1)[0].strip()
    return name_map.get(prefix)


def build_name_to_id(datasets: List[Dict]) -> Dict[str, str]:
    mapping: Dict[str, str] = {}
    for ds in datasets:
        name = ds.get('name') or ds.get('dataset_name')
        ds_id = ds.get('id') or ds.get('dataset_id')
        if name and ds_id:
            mapping[name] = ds_id
    return mapping


def iter_input_files(input_path: Path) -> List[Path]:
    if input_path.is_file():
        return [input_path]
    files: List[Path] = []
    for p in input_path.rglob('*'):
        if p.is_file() and p.suffix.lower() in {'.txt', '.md'}:
            files.append(p)
    return files


def main():
    parser = argparse.ArgumentParser(description='Upload processed documents to Dify datasets by filename prefix.')
    parser.add_argument('--input', required=True, help='File or directory containing processed documents (.txt/.md).')
    parser.add_argument('--dataset-token', default=os.getenv('DIFY_DATASET_API_KEY', 'dataset-30w7iO4HEz404YfOin1wm8rP'),
                        help='Dify Dataset API key. Can also be set via env DIFY_DATASET_API_KEY.')
    parser.add_argument('--api-base', default=None, help='Dify API base URL, e.g. http://your-dify/v1')
    parser.add_argument('--parent-sep', default='##', help='Parent segment separator.')
    parser.add_argument('--child-sep', default='\n', help='Child segment separator.')
    parser.add_argument('--parent-max', type=int, default=1024, help='Parent segment max length (tokens).')
    parser.add_argument('--child-max', type=int, default=512, help='Child segment max length (tokens).')
    args = parser.parse_args()

    root = Path(__file__).parent
    config_api_base = load_api_base_from_config(root / 'difyConfig.txt')
    api_base = args.api_base or config_api_base or 'http://dify.刘竹.cn/v1'

    client = DifyDatasetClient(api_base=api_base, dataset_api_key=args.dataset_token)

    try:
        datasets = client.get_all_datasets()
    except requests.HTTPError as e:
        print(f"Failed to list datasets: {e}")
        print("Ensure the provided Dataset API key has permission to list datasets, or provide dataset IDs manually.")
        return 1

    name_to_id = build_name_to_id(datasets)
    prefix_to_dataset = build_dataset_name_map()

    in_path = Path(args.input)
    files = iter_input_files(in_path)
    if not files:
        print(f"No files found under: {in_path}")
        return 0

    total = 0
    success = 0
    for file_path in files:
        total += 1
        ds_name = resolve_dataset_name_by_prefix(file_path.name, prefix_to_dataset)
        if not ds_name:
            print(f"Skip {file_path.name}: unknown prefix. Expected one of {list(prefix_to_dataset.keys())}")
            continue

        ds_id = name_to_id.get(ds_name)
        if not ds_id:
            print(f"Skip {file_path.name}: dataset '{ds_name}' not found in your workspace.")
            continue

        try:
            resp = client.upload_document_by_file(
                dataset_id=ds_id,
                file_path=file_path,
                parent_separator=args.parent_sep,
                child_separator=args.child_sep,
                parent_max_chars=args.parent_max,
                child_max_chars=args.child_max,
            )
            doc_id = resp.get('document', {}).get('id') or resp.get('id')
            print(f"Uploaded {file_path.name} to dataset '{ds_name}' (id={ds_id}). Document id: {doc_id}")
            success += 1
        except requests.HTTPError as e:
            try:
                err = e.response.json()
            except Exception:
                err = e.response.text if e.response is not None else str(e)
            print(f"Upload failed for {file_path.name}: {err}")
        except Exception as e:
            print(f"Upload failed for {file_path.name}: {e}")

    print(f"Done. Success {success}/{total}.")
    return 0


if __name__ == '__main__':
    sys.exit(main())


