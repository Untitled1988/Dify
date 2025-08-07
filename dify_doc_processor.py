import requests
import re
import os

API_BASE_URL = "http://dify.刘竹.cn/v1"
API_KEY = "app-rCTnmCw5c7DAZUST1fp4M9nQ"
LOCAL_FILE_PATH = r"C:\Users\liuleo2\OneDrive - Organon\SFE-销售指标设置.docx"
USER_ID = "liuzhu"

headers = {
    "Authorization": f"Bearer {API_KEY}"
}

def upload_file():
    url = f"{API_BASE_URL}/files/upload"
    with open(LOCAL_FILE_PATH, "rb") as f:
        files = {
            "file": ("1.docx", f, "application/vnd.openxmlformats-officedocument.wordprocessingml.document")
        }
        data = {"user": USER_ID}
        resp = requests.post(url, headers=headers, files=files, data=data)
    resp.raise_for_status()
    result = resp.json()
    print("Upload response:", result)
    return result["id"]

def trigger_workflow(file_id):
    url = f"{API_BASE_URL}/chat-messages"
    payload = {
        "query": "请帮我处理这个文档",
        "inputs": {
            "file": {
                "type": "document",
                "transfer_method": "local_file",
                "upload_file_id": file_id
            }
        },
        "response_mode": "blocking",
        "user": USER_ID
    }
    resp = requests.post(url, headers=headers, json=payload)
    resp.raise_for_status()
    result = resp.json()
    print("Workflow response:", result)
    return result

def extract_file_url(answer_text):
    match = re.search(r'\((/files/[^)]+)\)', answer_text)
    if match:
        return match.group(1)
    return None

def download_file_from_url(file_url, save_path):
    if file_url.startswith("/"):
        file_url = API_BASE_URL.replace("/v1", "") + file_url

    print(f"Downloading from: {file_url}")
    resp = requests.get(file_url, headers=headers, stream=True)
    resp.raise_for_status()
    with open(save_path, "wb") as f:
        for chunk in resp.iter_content(chunk_size=8192):
            if chunk:
                f.write(chunk)
    print(f"File downloaded to {save_path}")

def main():
    # 提取本地文件名
    original_basename = os.path.splitext(os.path.basename(LOCAL_FILE_PATH))[0]

    # 上传文件
    file_id = upload_file()

    # 调用 blocking 工作流
    workflow_result = trigger_workflow(file_id)
    answer = workflow_result.get("answer", "")
    print("AI 返回内容：", answer)

    # 提取下载链接
    file_url = extract_file_url(answer)
    if not file_url:
        print("未找到下载链接")
        return

    # 下载文件并保持原始文件名
    save_path = os.path.join(os.getcwd(), original_basename + ".txt")
    download_file_from_url(file_url, save_path)

if __name__ == "__main__":
    main()
