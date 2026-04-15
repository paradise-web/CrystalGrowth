# 晶体生长实验记录助手 - Android构建脚本
# 此脚本可以在Google Colab中运行

print("开始构建Android APK...")

# 安装必要的依赖
!apt-get update -y
!apt-get install -y build-essential git python3-pip openjdk-11-jdk
!pip3 install buildozer

# 克隆项目（用户需要替换为自己的GitHub仓库）
!git clone https://github.com/yourusername/exp_dec.git
%cd exp_dec
!git checkout feat/pack_android

# 构建APK
print("构建APK中...")
!buildozer android debug

# 检查构建结果
import os

apk_dir = 'bin'
if os.path.exists(apk_dir):
    apk_files = [f for f in os.listdir(apk_dir) if f.endswith('.apk')]
    if apk_files:
        print(f"构建成功！找到以下APK文件:")
        for apk in apk_files:
            print(f"- {apk}")
        print("\n请在Colab的文件浏览器中下载APK文件")
    else:
        print("构建失败，未找到APK文件")
        print("请查看构建日志以了解错误原因")
else:
    print("构建失败，bin目录不存在")
    print("请查看构建日志以了解错误原因")
