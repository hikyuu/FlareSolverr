import os
import platform
import shutil
import subprocess
import sys
import zipfile
import tarfile

import requests


def clean_files():
    try:
        shutil.rmtree(os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir, 'build'))
    except Exception:
        pass
    try:
        shutil.rmtree(os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir, 'dist'))
    except Exception:
        pass
    try:
        shutil.rmtree(os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir, 'dist_chrome'))
    except Exception:
        pass


def download_chromium():
    # https://commondatastorage.googleapis.com/chromium-browser-snapshots/index.html?prefix=Linux_x64/
    revision = "1681099" if os.name == 'nt' else '1681097'
    arch = 'Win_x64' if os.name == 'nt' else 'Linux_x64'
    dl_file = 'chrome-win' if os.name == 'nt' else 'chrome-linux'
    dl_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir, 'dist_chrome')
    dl_path_folder = os.path.join(dl_path, dl_file)
    dl_path_zip = dl_path_folder + '.zip'

    # response = requests.get(
    #     f'https://commondatastorage.googleapis.com/chromium-browser-snapshots/{arch}/LAST_CHANGE',
    #     timeout=30)
    # revision = response.text.strip()
    print("Downloading revision: " + revision)

    os.mkdir(dl_path)
    with requests.get(
            f'https://commondatastorage.googleapis.com/chromium-browser-snapshots/{arch}/{revision}/{dl_file}.zip',
            stream=True) as r:
        r.raise_for_status()
        with open(dl_path_zip, 'wb') as f:
            for chunk in r.iter_content(chunk_size=8192):
                f.write(chunk)
    print("File downloaded: " + dl_path_zip)
    with zipfile.ZipFile(dl_path_zip, 'r') as zip_ref:
        zip_ref.extractall(dl_path)
    os.remove(dl_path_zip)

    chrome_path = os.path.join(dl_path, "chrome")
    shutil.move(dl_path_folder, chrome_path)
    print("Extracted in: " + chrome_path)

    if os.name != 'nt':
        # Give executable permissions for *nix
        # file * | grep executable | cut -d: -f1
        print("Giving executable permissions...")
        execs = ['chrome', 'chrome_crashpad_handler', 'chrome_sandbox', 'chrome-wrapper']
        for exec_file in execs:
            exec_path = os.path.join(chrome_path, exec_file)
            os.chmod(exec_path, 0o755)


CHROME_FOR_TESTING_MILESTONES = (
    'https://googlechromelabs.github.io/chrome-for-testing/'
    'latest-versions-per-milestone-with-downloads.json'
)
CHROME_FOR_TESTING_KNOWN_GOOD = (
    'https://googlechromelabs.github.io/chrome-for-testing/'
    'known-good-versions-with-downloads.json'
)


def get_chromium_version():
    """读取 dist_chrome 里 Chromium 的完整版本号（用于挑选同版本的 chromedriver）。"""
    chrome_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir, 'dist_chrome', 'chrome')
    if not os.path.isdir(chrome_dir):
        raise Exception("没有找到 %s，请先执行 download_chromium()" % chrome_dir)
    if os.name == 'nt':
        import pefile
        pe = pefile.PE(os.path.join(chrome_dir, 'chrome.exe'), fast_load=True)
        pe.parse_data_directories(
            directories=[pefile.DIRECTORY_ENTRY["IMAGE_DIRECTORY_ENTRY_RESOURCE"]]
        )
        version = pe.FileInfo[0][0].StringTable[0].entries[b"FileVersion"].decode('utf-8')
    else:
        output = subprocess.run([os.path.join(chrome_dir, 'chrome'), '--version'],
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE).stdout
        version = output.decode('utf-8').strip().split()[-1]
    return version.strip()


def get_driver_platform():
    if os.name == 'nt':
        return 'win32'
    if sys.platform == 'darwin':
        return 'mac-x64'
    return 'linux64'


def resolve_chromedriver_url(chromium_version):
    """按 Chromium 大版本找 Chrome for Testing 的 chromedriver 下载地址。"""
    milestone = chromium_version.split('.')[0]
    platform_name = get_driver_platform()
    for api in (CHROME_FOR_TESTING_MILESTONES, CHROME_FOR_TESTING_KNOWN_GOOD):
        response = requests.get(api, timeout=30)
        response.raise_for_status()
        data = response.json()
        if 'milestones' in data:
            entry = data['milestones'].get(milestone)
            entries = [entry] if entry else []
        else:
            entries = [v for v in data.get('versions', [])
                       if v['version'].split('.')[0] == milestone]
        # 同一 milestone 内取最新的 patch 版本
        for entry in reversed(entries):
            for item in entry.get('downloads', {}).get('chromedriver', []):
                if item.get('platform') == platform_name:
                    return item['url']
    raise Exception("Chrome for Testing 里没有 Chromium %s 对应的 chromedriver" % chromium_version)


def patch_chromedriver(driver_path):
    """构建期打补丁；失败只告警，运行时 undetected_chromedriver 还会就地重试。"""
    try:
        from undetected_chromedriver.patcher import Patcher
        patcher = Patcher(executable_path=driver_path)
        if not patcher.is_binary_patched():
            patcher.patch_exe()
        print("chromedriver patched: %s" % patcher.is_binary_patched())
    except Exception as exc:
        print("WARNING: 构建期打补丁失败，运行时将就地重试：%s" % exc)


def download_chromedriver():
    """把与包内 Chromium 同版本的 chromedriver 放进 dist_chrome，随 PyInstaller 打包。"""
    version = get_chromium_version()
    url = resolve_chromedriver_url(version)
    print("Chromium %s -> chromedriver %s" % (version, url))

    dist_chrome = os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir, 'dist_chrome')
    zip_path = os.path.join(dist_chrome, 'chromedriver.zip')
    with requests.get(url, stream=True, timeout=60) as response:
        response.raise_for_status()
        with open(zip_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)

    with zipfile.ZipFile(zip_path, 'r') as zip_ref:
        zip_ref.extractall(dist_chrome)
    os.remove(zip_path)

    platform_name = get_driver_platform()
    exe_name = 'chromedriver.exe' if os.name == 'nt' else 'chromedriver'
    extracted = os.path.join(dist_chrome, 'chromedriver-' + platform_name)
    target = os.path.join(dist_chrome, exe_name)
    shutil.move(os.path.join(extracted, exe_name), target)
    os.chmod(target, 0o755)

    # BSD-3-Clause 要求保留版权声明，许可文件一起随包分发
    for name in ('LICENSE.chromedriver', 'THIRD_PARTY_NOTICES.chromedriver'):
        source = os.path.join(extracted, name)
        if os.path.exists(source):
            shutil.move(source, os.path.join(dist_chrome, name))

    patch_chromedriver(target)
    print("chromedriver ready: " + target)


def run_pyinstaller():
    sep = ';' if os.name == 'nt' else ':'
    # miao fork patch: --onedir 显式声明。PyInstaller 6.x 的默认值就是 onedir，
    # 但写死它才不会因为上游改默认值而让产物形态（单文件 vs 目录）静默变化。
    # miao fork patch: chromedriver 随包分发，运行时由 utils.get_bundled_driver_path()
    # 直接命中，不再联网下载。许可文件一并带上，满足 BSD-3-Clause 再分发要求。
    add_data = [
        f"package.json{sep}.",
        f"{os.path.join('dist_chrome', 'chrome')}{sep}chrome",
    ]
    for extra in ('chromedriver.exe', 'chromedriver',
                  'LICENSE.chromedriver', 'THIRD_PARTY_NOTICES.chromedriver'):
        path = os.path.join('dist_chrome', extra)
        if os.path.exists(path):
            add_data.append(f"{path}{sep}.")

    pyinstaller_args = [sys.executable, "-m", "PyInstaller",
                        "--onedir",
                        "--icon", "resources/flaresolverr_logo.ico"]
    for item in add_data:
        pyinstaller_args += ["--add-data", item]
    pyinstaller_args.append(os.path.join("src", "flaresolverr.py"))

    result = subprocess.run(pyinstaller_args,
                            cwd=os.pardir, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if result.returncode != 0:
        print(result.stderr.decode('utf-8'))
        raise Exception("Error running pyInstaller")


def compress_package():
    dist_folder = os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir, 'dist')
    package_folder = os.path.join(dist_folder, 'package')
    shutil.move(os.path.join(dist_folder, 'flaresolverr'), os.path.join(package_folder, 'flaresolverr'))
    print("Package folder: " + package_folder)

    compr_format = 'zip' if os.name == 'nt' else 'gztar'
    compr_file_name = 'flaresolverr_windows_x64' if os.name == 'nt' else 'flaresolverr_linux_x64'
    compr_file_path = os.path.join(dist_folder, compr_file_name)
    
    if compr_format == 'zip':
        shutil.make_archive(compr_file_path, compr_format, package_folder)
        print("Compressed file path: " + compr_file_path)
    else:
        def _reset_tarinfo(tarinfo):
            tarinfo.uid = 0
            tarinfo.gid = 0
            tarinfo.uname = ""
            tarinfo.gname = ""
            return tarinfo

        tar_path = compr_file_path + '.tar.gz'
        with tarfile.open(tar_path, 'w:gz') as tar:
            for entry in os.listdir(package_folder):
                fullpath = os.path.join(package_folder, entry)
                tar.add(fullpath, arcname=entry, filter=_reset_tarinfo)
        print("Compressed file path: " + tar_path)

if __name__ == "__main__":
    print("Building package...")
    print("Platform: " + platform.platform())

    print("Cleaning previous build...")
    clean_files()

    print("Downloading Chromium...")
    download_chromium()

    print("Downloading ChromeDriver...")
    download_chromedriver()

    print("Building pyinstaller executable... ")
    run_pyinstaller()

    print("Compressing package... ")
    compress_package()

# NOTE: python -m pip install pyinstaller
