# BleachBit CC（BleachBit 二开版）

> **本仓库是 [BleachBit](https://github.com/bleachbit/bleachbit) 6.0.6 的二次开发版本**（GPLv3），
> 目标：CCleaner 式的新手友好布局 + 补齐常用功能。所有修改遵循 GPL-3.0-or-later，
> 清理引擎与清理规则保持上游原样，便于合并上游更新。

## 相对上游 6.0.6 的修改

- **CCleaner 式四页布局**（一键清理 / 自定义清理 / 工具 / 选项，GTK3 StackSidebar），可随时切回经典界面
- **一键清理**：安全预设（自动排除 Cookie、密码、表单数据、空闲空间擦除等高危项），预览 → 清理两步流程
- **启动项管理**：注册表 Run/RunOnce（HKCU/HKLM 64/32 位视图）+ 启动文件夹，禁用可恢复
- **软件卸载器**：枚举已安装程序，优先静默卸载
- **重复文件查找**：大小分桶 + MD5 精确比对，后台线程可停止
- **磁盘分析**：目录占用聚合排序
- **注册表清理**：默认关闭，保守扫描四类，修复前自动导出 .reg 备份

## 运行

Windows 便携版见 Releases（未发布前可用源码运行：`python3 bleachbit.py`，Windows 需按
`windows/requirements.txt` 安装 PyGObject/GTK3，或直接使用官方 6.0.6 便携版 + 本仓库 `library.zip`
模块替换方案，见 `devtools`/ROADMAP 说明）。上游文档见下方原文。

---

# BleachBit

BleachBit cleans files to free disk space and to maintain privacy.


## Running from source

To run BleachBit without installation, first install the system dependencies,
then build the translations and run it:

```sh
make install-deps       # runtime deps (auto-detects Debian/Fedora/openSUSE/Arch)
make -C po local        # build translations
python3 bleachbit.py
```

Many Linux systems have the basic dependencies: you may skip installation,
but in case of any issues, please check for missing dependencies.

Then, review the preferences.

Then, select some options, and click Preview.  Review the files, toggle options accordingly, and click Delete.

For information regarding the command line interface, run:

```sh
python3 bleachbit.py --help
```

Read more about [running from source](https://docs.bleachbit.org/dev/running-from-source-code.html).

## Links

* [BleachBit home page](https://www.bleachbit.org)
* [Support](https://www.bleachbit.org/help)
* [Documentation](https://docs.bleachbit.org)

## Localization

Read [translation documentation](https://www.bleachbit.org/contribute/translate) or translate now in [Weblate](https://hosted.weblate.org/projects/bleachbit/), a web-based translation platform.

<a href="https://hosted.weblate.org/engage/bleachbit/">
      <img src="https://hosted.weblate.org/widgets/bleachbit/-/multi-auto.svg" alt="Translation status"/>
</a>

## Licenses

BleachBit itself, including source code and cleaner definitions, is licensed under the [GNU General Public License version 3](COPYING), or at your option, any later version.

markovify is licensed under the [MIT License](https://github.com/jsvine/markovify/blob/master/LICENSE.txt).

## Development

To develop, run the test suite, or build packages, install the
extra build/test/lint/packaging tools too:

```sh
make install-deps-dev
```

Common commands include:

```sh
make tests   # run tests
make lint    # check .py and .sh files for issues
make pretty  # format .py and .xml files
```

More resources:
* [![Build and Test](https://github.com/bleachbit/bleachbit/actions/workflows/build_and_test.yaml/badge.svg?branch=master)](https://github.com/bleachbit/bleachbit/actions/workflows/build_and_test.yaml)
* [![Run tests on macOS](https://github.com/bleachbit/bleachbit/actions/workflows/test_macos.yaml/badge.svg?branch=master)](https://github.com/bleachbit/bleachbit/actions/workflows/test_macos.yaml)
* [CleanerML Repository](https://github.com/bleachbit/cleanerml)
* [BleachBit Miscellaneous Repository](https://github.com/bleachbit/bleachbit-misc)
* [Winapp2.ini Repository](https://github.com/bleachbit/winapp2.ini)

### Docker-based Linux builds

The `docker/build.sh` script sets up a container, runs `make tests`,
and builds packages for a selected distribution. Usage:

```sh
./docker/build.sh <distro> # distro is one of {debian, fedora, opensuse}
```

Artifacts are copied to `./docker-artifacts/<distro>` on the host.
