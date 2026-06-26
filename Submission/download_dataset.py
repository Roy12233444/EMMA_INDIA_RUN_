import os
import sys

def main():
    repo_id = "armand0e/claude-fable-5-claude-code"
    local_dir = r"e:\EMMA_INDIA_RUN\Submission\claude-fable-5-claude-code"
    
    print(f"Attempting to download dataset '{repo_id}' to '{local_dir}'...")
    
    try:
        from huggingface_hub import snapshot_download
    except ImportError:
        print("huggingface_hub not installed. Installing it now...")
        import subprocess
        subprocess.check_call([sys.executable, "-m", "pip", "install", "huggingface_hub"])
        from huggingface_hub import snapshot_download

    try:
        snapshot_download(
            repo_id=repo_id,
            repo_type="dataset",
            local_dir=local_dir,
            ignore_patterns=["*.git*", "*.gitattributes"]
        )
        print("Download completed successfully!")
    except Exception as e:
        print(f"Error during download: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
