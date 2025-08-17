import os
import re
import json
import requests
import paramiko
from pathlib import Path
from tkinter import (
    Tk, ttk, Frame, Label, Button, Entry, Text, Listbox, Scrollbar,
    filedialog, messagebox, StringVar, BooleanVar, IntVar, END, MULTIPLE
)
from tkinter.messagebox import showerror
from typing import Optional, Dict, Any, List, Tuple
import threading


class ConfigManager:
    """配置管理器"""

    DEFAULT_CONFIG = {
        "TARGET_DIRECTORY": r"C:\Users\yiyue\MinerU",
        "MARKDOWN": {
            "IMAGE_URL_PREFIX": "https://127.0.0.1/images/"
        },
        "DIFY": {
            "ENABLED": True,
            "API_BASE_URL": "http://dify.刘竹.cn/v1",
            "API_KEY": "app-rCTnmCw5c7DAZUST1fp4M9nQ",
            "USER_ID": "liuzhu",
            "PROCESS_QUERY": "请帮我处理这个文档"
        },
        "DIFY_DATASET": {
            "ENABLED": True,
            "API_KEY": "dataset-30w7iO4HEz404YfOin1wm8rP",
            "PARENT_SEPARATOR": "##",
            "CHILD_SEPARATOR": "\\n",
            "PARENT_MAX_CHARS": 4000,
            "CHILD_MAX_CHARS": 1024,
            "INDEXING_TECHNIQUE": "high_quality"
        },
        "SFTP": {
            "ENABLED": True,
            "HOST": "8.141.18.37",
            "USER": "root",
            "PASS": "Liuzhu5635",
            "REMOTE_BASE": "2025",
            "PORT": 22
        }
    }

    CONFIG_FILENAME = "difyConfig.txt"

    @classmethod
    def load_config(cls) -> Dict[str, Any]:
        """加载配置文件"""
        config_path = Path(__file__).parent / cls.CONFIG_FILENAME

        if not config_path.exists():
            with open(config_path, 'w', encoding='utf-8') as f:
                json.dump(cls.DEFAULT_CONFIG, f, indent=4, ensure_ascii=False)
            return cls.DEFAULT_CONFIG

        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)

                def merge_dict(d1, d2):
                    for k, v in d2.items():
                        if k in d1 and isinstance(d1[k], dict) and isinstance(v, dict):
                            merge_dict(d1[k], v)
                        else:
                            d1[k] = v
                    return d1

                return merge_dict(cls.DEFAULT_CONFIG.copy(), config)
        except Exception as e:
            messagebox.showerror("配置错误", f"无法加载配置文件:\n{str(e)}")
            return cls.DEFAULT_CONFIG

    @classmethod
    def save_config(cls, config: Dict[str, Any]):
        """保存配置文件"""
        config_path = Path(__file__).parent / cls.CONFIG_FILENAME
        with open(config_path, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=4, ensure_ascii=False)


class MarkdownProcessor:
    """Markdown处理核心逻辑"""

    def __init__(self, config: Dict[str, Any]):
        self.config = config

    def process_markdown_content(self, content: str) -> str:
        """处理Markdown内容"""
        lines = content.split('\n')
        processed_lines = []
        i = 0
        n = len(lines)

        while i < n:
            line = lines[i]
            img_match = re.match(r'^!\[\]\((images/[a-f0-9]+\.jpg)\)\s*$', line)

            if img_match:
                img_path = img_match.group(1)
                next_line = lines[i + 1].strip() if i + 1 < n else ""

                if next_line == "":
                    caption = None
                    for j in range(i - 1, -1, -1):
                        title_match = re.match(r'^#+\s*(.*?)\s*$', lines[j])
                        if title_match:
                            caption = title_match.group(1)
                            break

                    if caption:
                        processed_lines.append(f'![{caption}]({img_path})')
                        if i + 1 < n and lines[i + 1].strip() == "":
                            i += 1
                    else:
                        processed_lines.append(line)

                elif next_line and not next_line.startswith(('!', '#')):
                    processed_lines.append(f'![{next_line}]({img_path})')
                    i += 1
                else:
                    processed_lines.append(line)

                i += 1

            elif line.startswith('#'):
                if re.match(r'^#\d+\.\d+\s', line):
                    line = re.sub(r'^#', '##', line, count=1)
                elif re.match(r'^#\d+\.\d+\.\d+\s', line):
                    line = re.sub(r'^#', '###', line, count=1)
                processed_lines.append(line)
                i += 1
            else:
                processed_lines.append(line)
                i += 1

        return '\n'.join(processed_lines)

    @staticmethod
    def extract_name_from_pdf_folder(folder_name: str) -> Optional[str]:
        """从文件夹名中提取名称"""
        match = re.search(r'^(.*?)\.pdf', folder_name, re.IGNORECASE)
        return match.group(1) if match else None

    def rename_images_and_update_md(self, md_filepath: str, images_folder: str) -> bool:
        """处理图片和Markdown文件"""
        try:
            base_name = Path(md_filepath).stem
            image_files = sorted(
                f for f in os.listdir(images_folder)
                if f.lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.bmp', '.webp'))
            )

            if not image_files:
                return False

            with open(md_filepath, 'r', encoding='utf-8') as f:
                md_content = self.process_markdown_content(f.read())

            for i, old_name in enumerate(image_files, start=1):
                ext = Path(old_name).suffix
                new_name = f"{base_name}_{i:02d}{ext}"
                old_path = Path(images_folder) / old_name
                new_path = Path(images_folder) / new_name

                old_path.rename(new_path)
                md_content = md_content.replace(old_name, new_name)

            prefix = self.config["MARKDOWN"].get("IMAGE_URL_PREFIX", "")
            md_content = md_content.replace(r'(images/', f'({prefix}')

            with open(md_filepath, 'w', encoding='utf-8') as f:
                f.write(md_content)

            return True
        except Exception as e:
            print(f"处理Markdown失败: {e}")
            return False

    def process_pdf_folders(self, target_dir: str, progress_callback=None) -> List[str]:
        """处理目录中的所有PDF文件夹"""
        processed_files = []
        target_path = Path(target_dir)

        for folder in target_path.iterdir():
            if not folder.is_dir():
                continue

            new_name_base = self.extract_name_from_pdf_folder(folder.name)
            if not new_name_base:
                continue

            old_md_path = folder / "full.md"
            if not old_md_path.exists():
                continue

            new_md_name = f"{new_name_base}.md"
            new_md_path = folder / new_md_name

            try:
                old_md_path.rename(new_md_path)
                images_folder = folder / "images"
                if images_folder.exists():
                    if self.rename_images_and_update_md(new_md_path, images_folder):
                        processed_files.append(str(new_md_path))
                        if progress_callback:
                            progress_callback(str(new_md_path))
            except Exception as e:
                print(f"处理文件夹 {folder} 失败: {e}")

        return processed_files


class DifyAPI:
    """Dify API交互"""

    def __init__(self, config: Dict[str, Any]):
        self.config = config["DIFY"]

    def upload_file(self, file_path: str) -> Optional[str]:
        """上传文件到Dify"""
        try:
            url = f"{self.config['API_BASE_URL']}/files/upload"
            headers = {"Authorization": f"Bearer {self.config['API_KEY']}"}

            with open(file_path, "rb") as f:
                files = {"file": (Path(file_path).name, f, "application/octet-stream")}
                data = {"user": self.config["USER_ID"]}
                resp = requests.post(url, headers=headers, files=files, data=data)
                resp.raise_for_status()
                return resp.json()["id"]
        except Exception as e:
            print(f"Dify上传失败: {e}")
            return None

    def trigger_workflow(self, file_id: str) -> Optional[Dict[str, Any]]:
        """触发工作流"""
        try:
            url = f"{self.config['API_BASE_URL']}/chat-messages"
            headers = {"Authorization": f"Bearer {self.config['API_KEY']}"}

            payload = {
                "query": self.config.get("PROCESS_QUERY", "请帮我处理这个文档"),
                "inputs": {
                    "file": {
                        "type": "document",
                        "transfer_method": "local_file",
                        "upload_file_id": file_id
                    }
                },
                "response_mode": "blocking",
                "user": self.config["USER_ID"]
            }

            resp = requests.post(url, headers=headers, json=payload)
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            print(f"触发工作流失败: {e}")
            return None

    def download_file(self, file_url: str, save_path: str) -> bool:
        """从Dify下载文件"""
        try:
            headers = {"Authorization": f"Bearer {self.config['API_KEY']}"}

            if file_url.startswith("/"):
                file_url = self.config["API_BASE_URL"].replace("/v1", "") + file_url

            with requests.get(file_url, headers=headers, stream=True) as resp:
                resp.raise_for_status()
                with open(save_path, "wb") as f:
                    for chunk in resp.iter_content(chunk_size=8192):
                        if chunk:
                            f.write(chunk)
            return True
        except Exception as e:
            print(f"下载文件失败: {e}")
            return False

    def process_file(self, file_path: str) -> Optional[str]:
        """完整处理流程"""
        file_id = self.upload_file(file_path)
        if not file_id:
            return None

        result = self.trigger_workflow(file_id)
        if not result:
            return None

        answer = result.get("answer", "")
        file_url = self.extract_file_url(answer)
        if not file_url:
            return None

        # 获取原始文件的目录
        original_dir = os.path.dirname(file_path)
        endwith = '.txt'
        result_filename = f"{Path(file_path).stem}{endwith}"
        # 组合完整路径
        save_path = os.path.join(original_dir, result_filename).replace("\\", "/")
        if self.download_file(file_url, save_path):
            return save_path
        return None

    @staticmethod
    def extract_file_url(answer_text: str) -> Optional[str]:
        """从回答中提取文件URL"""
        match = re.search(r'\((/files/[^)]+)\)', answer_text)
        return match.group(1) if match else None


class DifyDatasetClient:
    """Dify知识库数据集管理客户端"""

    def __init__(self, config: Dict[str, Any]):
        self.config = config["DIFY_DATASET"]
        self.api_base = config["DIFY"]["API_BASE_URL"].rstrip('/')
        self.token = self.config["API_KEY"]
        self.session = requests.Session()
        self.session.headers.update({
            'Authorization': f'Bearer {self.token}'
        })
        self.timeout = 60
        
        # 验证配置是否正确加载
        print(f"=== DifyDatasetClient 配置验证 ===")
        print(f"API基础URL: {self.api_base}")
        print(f"数据集API密钥: {self.token[:10]}...")
        print(f"父级分隔符: '{self.config.get('PARENT_SEPARATOR', 'NOT_SET')}'")
        print(f"子级分隔符: '{self.config.get('CHILD_SEPARATOR', 'NOT_SET')}'")
        print(f"父级最大字符: {self.config.get('PARENT_MAX_CHARS', 'NOT_SET')}")
        print(f"子级最大字符: {self.config.get('CHILD_MAX_CHARS', 'NOT_SET')}")
        print(f"索引技术: {self.config.get('INDEXING_TECHNIQUE', 'NOT_SET')}")
        print(f"=== 配置验证结束 ===\n")

    def list_datasets(self, page: int = 1, page_size: int = 100) -> Tuple[List[Dict], bool]:
        """列出数据集。返回 (datasets, has_more)"""
        url = f"{self.api_base}/datasets"
        params = {"page": page, "page_size": page_size}
        resp = self.session.get(url, params=params, timeout=self.timeout)
        resp.raise_for_status()
        data = resp.json()
        # 兼容可能的形状: {data: [...], has_more: bool} 或分页元数据
        datasets = data.get('data') if isinstance(data, dict) else data
        if datasets is None:
            datasets = data.get('items', [])
        total = data.get('total', None)
        has_more = False
        if total is not None:
            has_more = page * page_size < int(total)
        else:
            # 通过next/page信息回退
            has_more = bool(data.get('has_more'))
        return datasets or [], has_more

    def get_all_datasets(self) -> List[Dict]:
        """获取所有数据集"""
        page = 1
        all_items: List[Dict] = []
        while True:
            items, has_more = self.list_datasets(page=page)
            all_items.extend(items)
            if not has_more or not items:
                break
            page += 1
        return all_items

    def upload_document_by_file(self, dataset_id: str, file_path: Path) -> Dict:
        """将本地文件上传到数据集中，使用自定义的父子分段规则"""
        url = f"{self.api_base}/datasets/{dataset_id}/document/create-by-file"

        # 构建处理规则 - 只使用一种格式
        process_rule = {
            "mode": "hierarchical",
            "rules": {
                "pre_processing_rules": [
                    {"id": "remove_extra_spaces", "enabled": False},
                    {"id": "remove_urls_emails", "enabled": False}
                ],
                "segmentation": {
                    "separator": self.config["PARENT_SEPARATOR"],
                    "max_tokens": self.config["PARENT_MAX_CHARS"]
                },
                "parent_mode": "paragraph",
                "subchunk_segmentation": {
                    "separator": self.config["CHILD_SEPARATOR"],
                    "max_tokens": self.config["CHILD_MAX_CHARS"]
                }
            }
        }

        meta = {
            "name": file_path.name,
            "indexing_technique": self.config["INDEXING_TECHNIQUE"],
            "doc_form": "hierarchical_model",
            "process_rule": process_rule
        }

        # 详细的调试输出：检查参数传递
        print(f"\n=== 详细调试信息 ===")
        print(f"文件路径: {file_path}")
        print(f"数据集ID: {dataset_id}")
        print(f"配置中的父级分隔符: '{self.config['PARENT_SEPARATOR']}' (类型: {type(self.config['PARENT_SEPARATOR'])})")
        print(f"配置中的子级分隔符: '{self.config['CHILD_SEPARATOR']}' (类型: {type(self.config['CHILD_SEPARATOR'])})")
        print(f"配置中的父级最大字符: {self.config['PARENT_MAX_CHARS']} (类型: {type(self.config['PARENT_MAX_CHARS'])})")
        print(f"配置中的子级最大字符: {self.config['CHILD_MAX_CHARS']} (类型: {type(self.config['CHILD_MAX_CHARS'])})")
        print(f"索引技术: {self.config['INDEXING_TECHNIQUE']}")
        
        # 检查处理规则中的实际值
        print(f"\n处理规则详情:")
        print(f"  - 父级分隔符: '{process_rule['rules']['segmentation']['separator']}' (类型: {type(process_rule['rules']['segmentation']['separator'])})")
        print(f"  - 父级最大字符: {process_rule['rules']['segmentation']['max_tokens']} (类型: {type(process_rule['rules']['segmentation']['max_tokens'])})")
        print(f"  - 子级分隔符: '{process_rule['rules']['subchunk_segmentation']['separator']}' (类型: {type(process_rule['rules']['subchunk_segmentation']['separator'])})")
        print(f"  - 子级最大字符: {process_rule['rules']['subchunk_segmentation']['max_tokens']} (类型: {type(process_rule['rules']['subchunk_segmentation']['max_tokens'])})")
        
        # 检查JSON序列化后的结果
        json_meta = json.dumps(meta, ensure_ascii=False)
        print(f"\nJSON序列化后的元数据:")
        print(f"  - 长度: {len(json_meta)}")
        print(f"  - 内容: {json_meta}")
        
        # 检查是否包含我们的分隔符
        if self.config['PARENT_SEPARATOR'] in json_meta:
            print(f"✓ 父级分隔符 '{self.config['PARENT_SEPARATOR']}' 在JSON中找到")
        else:
            print(f"✗ 父级分隔符 '{self.config['PARENT_SEPARATOR']}' 在JSON中未找到!")
            
        if self.config['CHILD_SEPARATOR'] in json_meta:
            print(f"✓ 子级分隔符 '{self.config['CHILD_SEPARATOR']}' 在JSON中找到")
        else:
            print(f"✗ 子级分隔符 '{self.config['CHILD_SEPARATOR']}' 在JSON中未找到!")
        
        print(f"=== 调试信息结束 ===\n")

        files = {
            'file': (file_path.name, open(file_path, 'rb'), 'application/octet-stream')
        }
        
        data = {
            'data': json_meta
        }
        
        # 发送请求并检查响应
        print(f"发送请求到: {url}")
        print(f"请求头: {dict(self.session.headers)}")
        print(f"请求数据: {data}")
        
        resp = self.session.post(url, files=files, data=data, timeout=self.timeout)
        
        # 检查响应
        print(f"响应状态码: {resp.status_code}")
        print(f"响应头: {dict(resp.headers)}")
        
        try:
            resp_json = resp.json()
            print(f"响应内容: {json.dumps(resp_json, ensure_ascii=False, indent=2)}")
        except:
            print(f"响应文本: {resp.text}")
        
        resp.raise_for_status()
        return resp.json()


def build_dataset_name_map() -> Dict[str, str]:
    """构建文件名前缀到实际数据集名称的映射"""
    # 前缀 -> 数据集名称
    return {
        'Other': 'Other',
        '业务知识': '业务知识',
        '运维手册': '运维手册/SOP/KBA',
        'SOP': '运维手册/SOP/KBA',
        'KBA': '运维手册/SOP/KBA'
    }


def resolve_dataset_name_by_prefix(filename: str, name_map: Dict[str, str]) -> Optional[str]:
    """根据文件名前缀解析数据集名称"""
    prefix = Path(filename).stem.split('_', 1)[0].strip()
    return name_map.get(prefix)


def build_name_to_id(datasets: List[Dict]) -> Dict[str, str]:
    """构建数据集名称到ID的映射"""
    mapping: Dict[str, str] = {}
    for ds in datasets:
        name = ds.get('name') or ds.get('dataset_name')
        ds_id = ds.get('id') or ds.get('dataset_id')
        if name and ds_id:
            mapping[name] = ds_id
    return mapping


def iter_input_files(input_path: Path) -> List[Path]:
    """迭代输入文件"""
    if input_path.is_file():
        return [input_path]
    files: List[Path] = []
    for p in input_path.rglob('*'):
        if p.is_file() and p.suffix.lower() in {'.txt', '.md'}:
            files.append(p)
    return files


class SFTPUploader:
    """SFTP文件上传 - 支持多文件"""

    def __init__(self, config: Dict[str, Any]):
        self.config = config["SFTP"]
        self.transport = None
        self.sftp = None

    def connect(self) -> bool:
        """建立SFTP连接"""
        try:
            self.transport = paramiko.Transport((self.config["HOST"], self.config.get("PORT", 22)))
            self.transport.connect(username=self.config["USER"], password=self.config["PASS"])
            self.sftp = paramiko.SFTPClient.from_transport(self.transport)
            return True
        except Exception as e:
            print(f"SFTP连接失败: {e}")
            return False

    def disconnect(self):
        """关闭SFTP连接"""
        if self.sftp:
            self.sftp.close()
        if self.transport:
            self.transport.close()

    def ensure_remote_path(self, remote_path: str):
        """确保远程路径存在"""
        try:
            dirs = remote_path.split('/')
            current_path = ""
            for dir_name in dirs:
                if not dir_name:
                    continue
                current_path += f"/{dir_name}"
                try:
                    self.sftp.chdir(current_path)
                except IOError:
                    self.sftp.mkdir(current_path)
                    self.sftp.chdir(current_path)
        except Exception as e:
            print(f"远程连接失败: {e}")
            return False
    def upload_file(self, local_file: str, remote_path: str) -> bool:
        """上传单个文件"""
        try:
            remote_dir = os.path.dirname(remote_path)
            # print(remote_dir)
            if remote_dir:
                self.ensure_remote_path(remote_dir)

            self.sftp.put(local_file, remote_path)
            return True
        except Exception as e:
            print(f"文件上传失败 {local_file}: {e}")
            return False

    def upload_files(self, file_pairs: List[Tuple[str, str]]) -> Dict[str, bool]:
        """
        批量上传文件
        :param file_pairs: [(local_path, remote_path), ...]
        :return: {file_path: success}
        """
        results = {}
        if not self.connect():
            return {pair[0]: False for pair in file_pairs}

        try:
            for local_file, remote_path in file_pairs:
                success = self.upload_file(local_file, remote_path)
                results[local_file] = success
            return results
        finally:
            self.disconnect()

class SFTPFrame(Frame):
    """SFTP上传页面 - 支持多文件"""

    def __init__(self, parent, app):
        super().__init__(parent)
        self.app = app
        self.uploader = SFTPUploader(app.config)
        self.selected_files = []  # 存储选择的文件列表
        self.setup_ui()

    def setup_ui(self):
        """设置UI"""
        # 服务器配置
        Label(self, text="SFTP服务器:").grid(row=0, column=0, padx=5, pady=5, sticky='e')
        self.host_entry = Entry(self, width=30)
        self.host_entry.grid(row=0, column=1, padx=5, pady=5)
        self.host_entry.insert(0, self.app.config["SFTP"]["HOST"])

        Label(self, text="端口:").grid(row=0, column=2, padx=5, pady=5, sticky='e')
        self.port_entry = Entry(self, width=10)
        self.port_entry.grid(row=0, column=3, padx=5, pady=5)
        self.port_entry.insert(0, self.app.config["SFTP"].get("PORT", 22))

        Label(self, text="用户名:").grid(row=1, column=0, padx=5, pady=5, sticky='e')
        self.user_entry = Entry(self, width=30)
        self.user_entry.grid(row=1, column=1, padx=5, pady=5)
        self.user_entry.insert(0, self.app.config["SFTP"]["USER"])

        Label(self, text="密码:").grid(row=1, column=2, padx=5, pady=5, sticky='e')
        self.pass_entry = Entry(self, width=30, show="*")
        self.pass_entry.grid(row=1, column=3, padx=5, pady=5)
        self.pass_entry.insert(0, self.app.config["SFTP"]["PASS"])

        Label(self, text="远程基础路径:").grid(row=2, column=0, padx=5, pady=5, sticky='e')
        self.remote_base_entry = Entry(self, width=30)
        self.remote_base_entry.grid(row=2, column=1, padx=5, pady=5)
        self.remote_base_entry.insert(0, self.app.config["SFTP"]["REMOTE_BASE"])

        # 启用复选框
        self.enabled_var = BooleanVar(value=self.app.config["SFTP"]["ENABLED"])
        self.enabled_check = ttk.Checkbutton(self, text="启用SFTP上传", variable=self.enabled_var)
        self.enabled_check.grid(row=2, column=2, columnspan=2, padx=5, pady=5)

        # 文件列表
        Label(self, text="本地文件:").grid(row=3, column=0, padx=5, pady=5, sticky='e')

        self.file_listbox = Listbox(self, width=60, height=5, selectmode=MULTIPLE)
        self.file_listbox.grid(row=3, column=1, columnspan=2, padx=5, pady=5)

        scrollbar = Scrollbar(self, orient="vertical")
        scrollbar.config(command=self.file_listbox.yview)
        scrollbar.grid(row=3, column=3, sticky='ns')
        self.file_listbox.config(yscrollcommand=scrollbar.set)

        Button(self, text="添加文件...", command=self.add_files).grid(row=4, column=1, padx=5, pady=5)
        Button(self, text="移除选中", command=self.remove_selected).grid(row=4, column=2, padx=5, pady=5)

        # 远程路径模板
        Label(self, text="远程路径模板:").grid(row=5, column=0, padx=5, pady=5, sticky='e')
        self.remote_template = Entry(self, width=50)
        self.remote_template.grid(row=5, column=1, columnspan=2, padx=5, pady=5)
        self.remote_template.insert(0, f"/{self.app.config['SFTP']['REMOTE_BASE']}/{{filename}}")

        # 上传按钮
        Button(self, text="上传所有文件", command=self.upload_files).grid(row=6, column=1, pady=10)

        # 日志区域
        self.log_text = Text(self, height=10, width=80, state='disabled')
        self.log_text.grid(row=7, column=0, columnspan=4, padx=5, pady=5)

        # 滚动条
        scrollbar = ttk.Scrollbar(self, command=self.log_text.yview)
        scrollbar.grid(row=7, column=4, sticky='ns')
        self.log_text['yscrollcommand'] = scrollbar.set

    def add_files(self):
        """添加多个文件"""
        files = filedialog.askopenfilenames()
        if files:
            for f in files:
                if f not in self.selected_files:
                    self.selected_files.append(f)
                    self.file_listbox.insert(END, f)
            self.update_remote_paths()

    def remove_selected(self):
        """移除选中的文件"""
        selected_indices = self.file_listbox.curselection()
        for i in reversed(selected_indices):
            self.selected_files.pop(i)
            self.file_listbox.delete(i)

    def update_remote_paths(self):
        """根据模板更新远程路径"""
        template = self.remote_template.get()
        if "{" not in template:
            return

        # 这里可以添加更复杂的模板解析逻辑
        # 当前简单实现只替换{filename}
        for i, local_file in enumerate(self.selected_files):
            filename = os.path.basename(local_file)
            remote_path = template.format(filename=filename)

    def log_message(self, message: str):
        """记录日志"""
        self.log_text.config(state='normal')
        self.log_text.insert('end', message + '\n')
        self.log_text.see('end')
        self.log_text.config(state='disabled')
        self.app.update()

    def upload_files(self):
        """上传所有文件"""
        if not self.selected_files:
            messagebox.showerror("错误", "请先添加要上传的文件")
            return

        # 更新配置
        self.app.config["SFTP"]["HOST"] = self.host_entry.get()
        self.app.config["SFTP"]["PORT"] = int(self.port_entry.get())
        self.app.config["SFTP"]["USER"] = self.user_entry.get()
        self.app.config["SFTP"]["PASS"] = self.pass_entry.get()
        self.app.config["SFTP"]["REMOTE_BASE"] = self.remote_base_entry.get()
        self.app.config["SFTP"]["ENABLED"] = self.enabled_var.get()
        self.app.save_config()

        # 准备文件对 (本地路径, 远程路径)
        template = self.remote_template.get()
        file_pairs = []
        for local_file in self.selected_files:
            filename = os.path.basename(local_file)
            remote_path = template.format(filename=filename)
            file_pairs.append((local_file, remote_path))

        # 在后台线程中上传
        def upload():
            self.app.update_status("正在上传文件...")
            self.log_message(f"开始批量上传 {len(file_pairs)} 个文件")

            results = self.uploader.upload_files(file_pairs)

            success_count = sum(1 for r in results.values() if r)
            fail_count = len(results) - success_count

            self.log_message(f"上传完成! 成功: {success_count}, 失败: {fail_count}")

            for file, success in results.items():
                status = "成功" if success else "失败"
                self.log_message(f"- {os.path.basename(file)}: {status}")

            self.app.update_status("上传完成")
            if fail_count == 0:
                messagebox.showinfo("成功", "所有文件上传成功!")
            else:
                messagebox.showwarning("完成",
                                       f"上传完成! 成功 {success_count} 个, 失败 {fail_count} 个")

        threading.Thread(target=upload, daemon=True).start()


class MarkdownFrame(Frame):
    """Markdown处理页面"""

    def __init__(self, parent, app):
        super().__init__(parent)
        self.app = app
        self.processor = MarkdownProcessor(app.config)
        self.setup_ui()

    def setup_ui(self):
        """设置UI"""
        # 目标目录选择
        Label(self, text="目标目录:").grid(row=0, column=0, padx=5, pady=5, sticky='e')
        self.dir_entry = Entry(self, width=50)
        self.dir_entry.grid(row=0, column=1, padx=5, pady=5)
        self.dir_entry.insert(0, self.app.config["TARGET_DIRECTORY"])

        Button(self, text="浏览...", command=self.browse_directory).grid(row=0, column=2, padx=5, pady=5)

        # 图片URL前缀
        Label(self, text="图片URL前缀:").grid(row=1, column=0, padx=5, pady=5, sticky='e')
        self.prefix_entry = Entry(self, width=50)
        self.prefix_entry.grid(row=1, column=1, padx=5, pady=5)
        self.prefix_entry.insert(0, self.app.config["MARKDOWN"].get("IMAGE_URL_PREFIX", ""))

        # 处理按钮
        Button(self, text="开始处理", command=self.start_processing).grid(row=2, column=1, pady=10)

        # 日志区域
        self.log_text = Text(self, height=15, width=80, state='disabled')
        self.log_text.grid(row=3, column=0, columnspan=3, padx=5, pady=5)

        # 滚动条
        scrollbar = ttk.Scrollbar(self, command=self.log_text.yview)
        scrollbar.grid(row=3, column=3, sticky='ns')
        self.log_text['yscrollcommand'] = scrollbar.set

    def browse_directory(self):
        """浏览目录"""
        dir_path = filedialog.askdirectory()
        if dir_path:
            self.dir_entry.delete(0, 'end')
            self.dir_entry.insert(0, dir_path)

    def log_message(self, message: str):
        """记录日志"""
        self.log_text.config(state='normal')
        self.log_text.insert('end', message + '\n')
        self.log_text.see('end')
        self.log_text.config(state='disabled')
        self.app.update()

    def start_processing(self):
        """开始处理"""
        # 更新配置
        self.app.config["TARGET_DIRECTORY"] = self.dir_entry.get()
        self.app.config["MARKDOWN"]["IMAGE_URL_PREFIX"] = self.prefix_entry.get()
        self.app.save_config()

        # 清空日志
        self.log_text.config(state='normal')
        self.log_text.delete(1.0, 'end')
        self.log_text.config(state='disabled')

        # 在后台线程中处理
        def process():
            self.app.update_status("正在处理Markdown文件...")
            self.log_message(f"开始处理目录: {self.dir_entry.get()}")

            processed_files = self.processor.process_pdf_folders(
                self.dir_entry.get(),
                progress_callback=lambda f: self.log_message(f"已处理: {f}")
            )

            self.log_message(f"\n处理完成! 共处理了 {len(processed_files)} 个文件")
            self.app.update_status("Markdown处理完成")
            messagebox.showinfo("完成", "Markdown处理完成!")

        threading.Thread(target=process, daemon=True).start()


class DifyFrame(Frame):
    """Dify处理页面 - 支持批量文件处理"""

    def __init__(self, parent, app):
        super().__init__(parent)
        self.app = app
        self.dify = DifyAPI(app.config)
        self.selected_files = []  # 存储选择的文件列表
        self.setup_ui()

    def setup_ui(self):
        """设置UI"""
        # API配置
        Label(self, text="API基础URL:").grid(row=0, column=0, padx=5, pady=5, sticky='e')
        self.api_url_entry = Entry(self, width=50)
        self.api_url_entry.grid(row=0, column=1, columnspan=2, padx=5, pady=5)
        self.api_url_entry.insert(0, self.app.config["DIFY"]["API_BASE_URL"])

        Label(self, text="API密钥:").grid(row=1, column=0, padx=5, pady=5, sticky='e')
        self.api_key_entry = Entry(self, width=50)
        self.api_key_entry.grid(row=1, column=1, columnspan=2, padx=5, pady=5)
        self.api_key_entry.insert(0, self.app.config["DIFY"]["API_KEY"])

        Label(self, text="用户ID:").grid(row=2, column=0, padx=5, pady=5, sticky='e')
        self.user_id_entry = Entry(self, width=30)
        self.user_id_entry.grid(row=2, column=1, padx=5, pady=5)
        self.user_id_entry.insert(0, self.app.config["DIFY"]["USER_ID"])

        Label(self, text="处理指令:").grid(row=3, column=0, padx=5, pady=5, sticky='e')
        self.query_entry = Entry(self, width=50)
        self.query_entry.grid(row=3, column=1, columnspan=2, padx=5, pady=5)
        self.query_entry.insert(0, self.app.config["DIFY"].get("PROCESS_QUERY", "请帮我处理这个文档"))

        # 启用复选框
        self.enabled_var = BooleanVar(value=self.app.config["DIFY"]["ENABLED"])
        self.enabled_check = ttk.Checkbutton(self, text="启用Dify处理", variable=self.enabled_var)
        self.enabled_check.grid(row=4, column=1, padx=5, pady=5)

        # 文件选择 - 改为多文件选择
        Label(self, text="选择文件:").grid(row=5, column=0, padx=5, pady=5, sticky='e')

        self.file_listbox = Listbox(self, width=60, height=5, selectmode=MULTIPLE)
        self.file_listbox.grid(row=5, column=1, columnspan=2, padx=5, pady=5)

        scrollbar = Scrollbar(self, orient="vertical")
        scrollbar.config(command=self.file_listbox.yview)
        scrollbar.grid(row=5, column=3, sticky='ns')
        self.file_listbox.config(yscrollcommand=scrollbar.set)

        Button(self, text="添加文件...", command=self.add_files).grid(row=6, column=1, padx=5, pady=5)
        Button(self, text="移除选中", command=self.remove_selected).grid(row=6, column=2, padx=5, pady=5)

        # 处理按钮
        Button(self, text="开始处理所有文件", command=self.process_files).grid(row=7, column=1, pady=10)

        # 日志区域
        self.log_text = Text(self, height=10, width=80, state='disabled')
        self.log_text.grid(row=8, column=0, columnspan=3, padx=5, pady=5)

        # 滚动条
        scrollbar = ttk.Scrollbar(self, command=self.log_text.yview)
        scrollbar.grid(row=8, column=3, sticky='ns')
        self.log_text['yscrollcommand'] = scrollbar.set

    def add_files(self):
        """添加多个文件"""
        files = filedialog.askopenfilenames()
        if files:
            for f in files:
                if f not in self.selected_files:
                    self.selected_files.append(f)
                    self.file_listbox.insert(END, f)

    def remove_selected(self):
        """移除选中的文件"""
        selected_indices = self.file_listbox.curselection()
        for i in reversed(selected_indices):
            self.selected_files.pop(i)
            self.file_listbox.delete(i)

    def log_message(self, message: str):
        """记录日志"""
        self.log_text.config(state='normal')
        self.log_text.insert('end', message + '\n')
        self.log_text.see('end')
        self.log_text.config(state='disabled')
        self.app.update()

    def process_files(self):
        """批量处理所有选中的文件"""
        # 更新配置
        self.app.config["DIFY"]["API_BASE_URL"] = self.api_url_entry.get()
        self.app.config["DIFY"]["API_KEY"] = self.api_key_entry.get()
        self.app.config["DIFY"]["USER_ID"] = self.user_id_entry.get()
        self.app.config["DIFY"]["PROCESS_QUERY"] = self.query_entry.get()
        self.app.config["DIFY"]["ENABLED"] = self.enabled_var.get()
        self.app.save_config()

        if not self.selected_files:
            messagebox.showerror("错误", "请先添加要处理的文件")
            return

        # 在后台线程中处理
        def process():
            self.app.update_status("正在批量处理文件...")
            self.log_message(f"开始批量处理 {len(self.selected_files)} 个文件")

            success_count = 0
            for file_path in self.selected_files:
                self.log_message(f"\n正在处理文件: {file_path}")
                result_path = self.dify.process_file(file_path)
                if result_path:
                    self.log_message(f"处理成功! 结果已保存到: {result_path}")
                    success_count += 1
                else:
                    self.log_message("处理失败!")

            self.log_message(f"\n批量处理完成! 成功: {success_count}, 失败: {len(self.selected_files) - success_count}")
            self.app.update_status("批量处理完成")

            if success_count == len(self.selected_files):
                messagebox.showinfo("成功", "所有文件处理成功!")
            else:
                messagebox.showwarning("完成",
                                       f"处理完成! 成功 {success_count} 个, 失败 {len(self.selected_files) - success_count} 个")

        threading.Thread(target=process, daemon=True).start()


class DifyDatasetFrame(Frame):
    """Dify知识库数据集管理页面"""

    def __init__(self, parent, app):
        super().__init__(parent)
        self.app = app
        self.dataset_client = DifyDatasetClient(app.config)
        self.selected_files = []
        self.datasets = []
        self.setup_ui()

    def setup_ui(self):
        """设置UI"""
        # API配置
        Label(self, text="API基础URL:").grid(row=0, column=0, padx=5, pady=5, sticky='e')
        self.api_url_entry = Entry(self, width=50)
        self.api_url_entry.grid(row=0, column=1, columnspan=2, padx=5, pady=5)
        self.api_url_entry.insert(0, self.app.config["DIFY"]["API_BASE_URL"])

        Label(self, text="数据集API密钥:").grid(row=1, column=0, padx=5, pady=5, sticky='e')
        self.dataset_api_key_entry = Entry(self, width=50)
        self.dataset_api_key_entry.grid(row=1, column=1, columnspan=2, padx=5, pady=5)
        self.dataset_api_key_entry.insert(0, self.app.config["DIFY_DATASET"]["API_KEY"])

        # 分段配置
        Label(self, text="父级分隔符:").grid(row=2, column=0, padx=5, pady=5, sticky='e')
        self.parent_sep_entry = Entry(self, width=20)
        self.parent_sep_entry.grid(row=2, column=1, padx=5, pady=5)
        self.parent_sep_entry.insert(0, self.app.config["DIFY_DATASET"]["PARENT_SEPARATOR"])

        Label(self, text="子级分隔符:").grid(row=2, column=2, padx=5, pady=5, sticky='e')
        self.child_sep_entry = Entry(self, width=20)
        self.child_sep_entry.grid(row=2, column=3, padx=5, pady=5)
        self.child_sep_entry.insert(0, self.app.config["DIFY_DATASET"]["CHILD_SEPARATOR"])

        Label(self, text="父级最大字符:").grid(row=3, column=0, padx=5, pady=5, sticky='e')
        self.parent_max_entry = Entry(self, width=20)
        self.parent_max_entry.grid(row=3, column=1, padx=5, pady=5)
        self.parent_max_entry.insert(0, str(self.app.config["DIFY_DATASET"]["PARENT_MAX_CHARS"]))

        Label(self, text="子级最大字符:").grid(row=3, column=2, padx=5, pady=5, sticky='e')
        self.child_max_entry = Entry(self, width=20)
        self.child_max_entry.grid(row=3, column=3, padx=5, pady=5)
        self.child_max_entry.insert(0, str(self.app.config["DIFY_DATASET"]["CHILD_MAX_CHARS"]))

        # 启用复选框
        self.enabled_var = BooleanVar(value=self.app.config["DIFY_DATASET"]["ENABLED"])
        self.enabled_check = ttk.Checkbutton(self, text="启用知识库上传", variable=self.enabled_var)
        self.enabled_check.grid(row=4, column=1, columnspan=2, padx=5, pady=5)

        # 数据集信息
        Label(self, text="可用数据集:").grid(row=5, column=0, padx=5, pady=5, sticky='e')
        self.dataset_listbox = Listbox(self, width=60, height=3)
        self.dataset_listbox.grid(row=5, column=1, columnspan=2, padx=5, pady=5)

        Button(self, text="刷新数据集", command=self.refresh_datasets).grid(row=5, column=3, padx=5, pady=5)

        # 文件选择
        Label(self, text="选择文件:").grid(row=6, column=0, padx=5, pady=5, sticky='e')

        self.file_listbox = Listbox(self, width=60, height=5, selectmode=MULTIPLE)
        self.file_listbox.grid(row=6, column=1, columnspan=2, padx=5, pady=5)

        scrollbar = Scrollbar(self, orient="vertical")
        scrollbar.config(command=self.file_listbox.yview)
        scrollbar.grid(row=6, column=3, sticky='ns')
        self.file_listbox.config(yscrollcommand=scrollbar.set)

        Button(self, text="添加文件...", command=self.add_files).grid(row=7, column=1, padx=5, pady=5)
        Button(self, text="移除选中", command=self.remove_selected).grid(row=7, column=2, padx=5, pady=5)

        # 上传按钮
        Button(self, text="开始上传到知识库", command=self.upload_to_datasets).grid(row=8, column=1, pady=10)

        # 日志区域
        self.log_text = Text(self, height=10, width=80, state='disabled')
        self.log_text.grid(row=9, column=0, columnspan=3, padx=5, pady=5)

        # 滚动条
        scrollbar = ttk.Scrollbar(self, command=self.log_text.yview)
        scrollbar.grid(row=9, column=3, sticky='ns')
        self.log_text['yscrollcommand'] = scrollbar.set

        # 初始化数据集列表
        self.refresh_datasets()

    def add_files(self):
        """添加多个文件"""
        files = filedialog.askopenfilenames()
        if files:
            for f in files:
                if f not in self.selected_files:
                    self.selected_files.append(f)
                    self.file_listbox.insert(END, f)

    def remove_selected(self):
        """移除选中的文件"""
        selected_indices = self.file_listbox.curselection()
        for i in reversed(selected_indices):
            self.selected_files.pop(i)
            self.file_listbox.delete(i)

    def refresh_datasets(self):
        """刷新数据集列表"""
        try:
            self.datasets = self.dataset_client.get_all_datasets()
            self.dataset_listbox.delete(0, END)
            for ds in self.datasets:
                name = ds.get('name') or ds.get('dataset_name', 'Unknown')
                ds_id = ds.get('id') or ds.get('dataset_id', 'Unknown')
                self.dataset_listbox.insert(END, f"{name} (ID: {ds_id})")
            self.log_message(f"已加载 {len(self.datasets)} 个数据集")
        except Exception as e:
            self.log_message(f"加载数据集失败: {e}")

    def log_message(self, message: str):
        """记录日志"""
        self.log_text.config(state='normal')
        self.log_text.insert('end', message + '\n')
        self.log_text.see('end')
        self.log_text.config(state='disabled')
        self.app.update()

    def upload_to_datasets(self):
        """上传文件到知识库数据集"""
        # 更新配置
        self.app.config["DIFY"]["API_BASE_URL"] = self.api_url_entry.get()
        self.app.config["DIFY_DATASET"]["API_KEY"] = self.dataset_api_key_entry.get()
        self.app.config["DIFY_DATASET"]["PARENT_SEPARATOR"] = self.parent_sep_entry.get()
        self.app.config["DIFY_DATASET"]["CHILD_SEPARATOR"] = self.child_sep_entry.get()
        self.app.config["DIFY_DATASET"]["PARENT_MAX_CHARS"] = int(self.parent_max_entry.get())
        self.app.config["DIFY_DATASET"]["CHILD_MAX_CHARS"] = int(self.child_max_entry.get())
        self.app.config["DIFY_DATASET"]["ENABLED"] = self.enabled_var.get()
        self.app.save_config()

        if not self.selected_files:
            messagebox.showerror("错误", "请先添加要上传的文件")
            return

        if not self.datasets:
            messagebox.showerror("错误", "没有可用的数据集，请先刷新数据集列表")
            return

        # 在后台线程中上传
        def upload():
            self.app.update_status("正在上传文件到知识库...")
            self.log_message(f"开始批量上传 {len(self.selected_files)} 个文件到知识库")

            # 重新初始化客户端（使用更新后的配置）
            self.dataset_client = DifyDatasetClient(self.app.config)
            
            # 获取数据集映射
            name_to_id = build_name_to_id(self.datasets)
            prefix_to_dataset = build_dataset_name_map()

            total = 0
            success = 0
            for file_path in self.selected_files:
                total += 1
                file_path_obj = Path(file_path)
                
                # 根据文件名前缀确定数据集
                ds_name = resolve_dataset_name_by_prefix(file_path_obj.name, prefix_to_dataset)
                if not ds_name:
                    self.log_message(f"跳过 {file_path_obj.name}: 未知前缀。期望的前缀: {list(prefix_to_dataset.keys())}")
                    continue

                ds_id = name_to_id.get(ds_name)
                if not ds_id:
                    self.log_message(f"跳过 {file_path_obj.name}: 数据集 '{ds_name}' 在工作区中未找到")
                    continue

                try:
                    # 记录上传前的配置信息
                    self.log_message(f"\n--- 上传文件: {file_path_obj.name} ---")
                    self.log_message(f"目标数据集: {ds_name} (ID: {ds_id})")
                    self.log_message(f"当前配置:")
                    self.log_message(f"  父级分隔符: '{self.dataset_client.config['PARENT_SEPARATOR']}'")
                    self.log_message(f"  子级分隔符: '{self.dataset_client.config['CHILD_SEPARATOR']}'")
                    self.log_message(f"  父级最大字符: {self.dataset_client.config['PARENT_MAX_CHARS']}")
                    self.log_message(f"  子级最大字符: {self.dataset_client.config['CHILD_MAX_CHARS']}")
                    self.log_message(f"  索引技术: {self.dataset_client.config['INDEXING_TECHNIQUE']}")
                    
                    resp = self.dataset_client.upload_document_by_file(
                        dataset_id=ds_id,
                        file_path=file_path_obj
                    )
                    doc_id = resp.get('document', {}).get('id') or resp.get('id')
                    self.log_message(f"成功上传 {file_path_obj.name} 到数据集 '{ds_name}' (ID={ds_id})。文档ID: {doc_id}")
                    success += 1
                except requests.HTTPError as e:
                    try:
                        err = e.response.json()
                    except Exception:
                        err = e.response.text if e.response is not None else str(e)
                    self.log_message(f"上传失败 {file_path_obj.name}: {err}")
                except Exception as e:
                    self.log_message(f"上传失败 {file_path_obj.name}: {e}")

            self.log_message(f"\n批量上传完成! 成功: {success}, 失败: {total - success}")
            self.app.update_status("知识库上传完成")

            if success == total:
                messagebox.showinfo("成功", "所有文件上传成功!")
            else:
                messagebox.showwarning("完成",
                                       f"上传完成! 成功 {success} 个, 失败 {total - success} 个")

        threading.Thread(target=upload, daemon=True).start()


class Application(Tk):
    """主应用程序GUI"""

    def __init__(self):
        super().__init__()
        self.title("文档处理工具")
        self.geometry("800x600")
        self.config = ConfigManager.load_config()

        # 创建笔记本式界面
        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill='both', expand=True)

        # 创建三个标签页
        self.markdown_frame = MarkdownFrame(self.notebook, self)
        self.sftp_frame = SFTPFrame(self.notebook, self)
        self.dify_frame = DifyFrame(self.notebook, self)
        self.dify_dataset_frame = DifyDatasetFrame(self.notebook, self)

        self.notebook.add(self.markdown_frame, text="Markdown处理")
        self.notebook.add(self.sftp_frame, text="SFTP上传")
        self.notebook.add(self.dify_frame, text="Dify处理")
        self.notebook.add(self.dify_dataset_frame, text="Dify数据集")

        # 状态栏
        self.status_var = StringVar()
        self.status_bar = Label(self, textvariable=self.status_var, bd=1, relief='sunken', anchor='w')
        self.status_bar.pack(side='bottom', fill='x')

        self.update_status("就绪")

    def update_status(self, message: str):
        """更新状态栏"""
        self.status_var.set(message)
        self.update()

    def save_config(self):
        """保存配置"""
        ConfigManager.save_config(self.config)
        self.update_status("配置已保存")


if __name__ == "__main__":
    app = Application()
    app.mainloop()