[app]

# (str) Title of your application
title = 晶体生长实验记录助手

# (str) Package name
package.name = expdec

# (str) Package domain (needed for android/ios packaging)
package.domain = com.expdec

# (str) Source code where the main.py live
source.dir = .

# (list) Source files to include (let empty to include all the files)
source.include_exts = py,png,jpg,kv,atlas

# (list) List of inclusions using pattern matching
#source.include_patterns = assets/*,images/*.png

# (list) Source files to exclude (let empty to not exclude anything)
#source.exclude_exts = spec

# (list) List of directory to exclude (let empty to not exclude anything)
#source.exclude_dirs = tests, bin

# (list) List of exclusions using pattern matching
#source.exclude_patterns = license,images/*/*.jpg

# (str) Application versioning (method 1)
version = 1.0

# (str) Application versioning (method 2) 
# version.regex = __version__ = ['"](.*)['"]
# version.filename = %(source.dir)s/main.py

# (list) Application requirements
# comma separated e.g. requirements = sqlite3,kivy
requirements = python3,kivy,kivymd,pillow,requests

# (str) Custom source folders for requirements
# Sets custom source for any requirements with recipes
# requirements.source.kivy = ../../kivy

# (list) Garden requirements
#garden_requirements =

# (str) Presplash of the application
#presplash.filename = %(source.dir)s/data/presplash.png

# (str) Icon of the application
#icon.filename = %(source.dir)s/data/icon.png

# (str) Supported orientation (one of landscape, portrait or all)
orientation = portrait

# (list) List of service to declare
#services =

#
# OSX Specific
#

# (str) OSX bundle identifier
#osx.python_version = 3
#osx.kivy_version = 1.9.1
#osx.bundle_identifier = org.test.myapp

#
# Android specific
#

# (bool) Indicate if the application should be fullscreen or not
fullscreen = 0

# (string) Presplash background color (for android toolchain)
# Supported formats are: #RRGGBB #AARRGGBB or one of the following names: 
# red, blue, green, black, white, gray, cyan, magenta, yellow, lightgray, darkgray, grey, lightgrey, darkgrey, aqua, fuchsia, lime, maroon, navy, olive, purple, silver, teal.
#android.presplash_color = #FFFFFF

# (string) Presplash animation using Lottie format. 
# see https://lottiefiles.com/ for examples and https://airbnb.design/lottie/ for general documentation. 
# Lottie files can be created using various tools, like Adobe After Effect or Synfig.
#android.presplash_lottie = "path/to/lottie/file.json"

# (str) Adaptive icon of the application (used if Android API level is 26+ at runtime)
#icon.adaptive_foreground.filename = %(source.dir)s/data/icon_fg.png
#icon.adaptive_background.filename = %(source.dir)s/data/icon_bg.png

# (list) Permissions
android.permissions = INTERNET,READ_EXTERNAL_STORAGE,WRITE_EXTERNAL_STORAGE,CAMERA

# (list) features (adds uses-feature -tags to manifest)
#android.features = android.hardware.usb.host

# (int) Target Android API, should be as high as possible.
android.api = 31

# (int) Minimum API your APK / AAB will support.
android.minapi = 21

# (int) Android SDK version to use
#android.sdk = 24

# (str) Android NDK version to use
android.ndk = 25b

# (int) Android NDK API to use. This is the minimum API your app will support, it should usually match android.minapi.
android.ndk_api = 21

# (bool) Use --private data storage (True) or --dir public storage (False)
#android.private_storage = True

# (str) Android NDK directory (if empty, it will be automatically downloaded.)
#android.ndk_path = 

# (str) Android SDK directory (if empty, it will be automatically downloaded.)
#android.sdk_path = 

# (str) ANT directory (if empty, it will be automatically downloaded.)
#android.ant_path = 

# (str) Gradle directory (if empty, it will be automatically downloaded.)
#android.gradle_path = 

# (bool) Automatically detect if an app already exists in the target device and remove it before installing the new one
#android.install_mode = dragndrop

# (str) Android entry point, default is ok for Kivy-based app
#android.entrypoint = org.kivy.android.PythonActivity

# (str) Android app theme, default is ok for Kivy-based app
# android.apptheme = @android:style/Theme.Holo.Light

# (list) Pattern to whitelist for the whole project
#android.whitelist = 

# (str) Path to a custom whitelist file
#android.whitelist_src = 

# (str) Path to a custom blacklist file
#android.blacklist_src = 

# (list) List of Java .jar files to add to the libs so that pyjnius can access it
#android.add_jars = foo.jar,bar.jar

# (list) List of Java files to add to the android project (can be java or a directory containing the files)
#android.add_src = 

# (list) Android AAR archives to add (currently works only with sdl2_gradle 
# android.api >= 28)
#android.add_aars = 

# (list) Gradle dependencies to add
#android.gradle_dependencies = 

# (bool) Enable AndroidX support. Enable when 'android.api >= 28'
#android.enable_androidx = True

# (list) add java compile options
# this can for example be necessary if you need to compile against Java 8 or higher
# see https://developer.android.com/studio/write/java8-support for more information
# android.add_compile_options = "-source 1.8 -target 1.8"

# (list) Gradle repositories to add {can be necessary for some dependencies}
#android.gradle_repositories = 

# (list) Gradle plugins to add
#android.gradle_plugins = 

# (list) additions to the build.gradle file
#android.build_gradle_additions = 

# (str) optional default directory to store the native libs after build
#android.libdir = libs

# (bool) Keep the source code when packaging the app
#android.keep_src = 

# (list) The Android arch to build for, choices: armeabi-v7a, arm64-v8a, x86, x86_64
android.archs = armeabi-v7a

# (int) overrides automatic versionCode computation (used in build.gradle)
# this is not the same as app version and should only be edited if you know what you're doing
# android.numeric_version = 1

# (bool) enables Android auto backup feature (Android API >=23)
android.allow_backup = True

# (str) XML file to include as an intent filters in <activity> tag
# android.manifest.intent_filters = 

# (str) launchMode to set for the main activity
#android.manifest.launch_mode = standard

# (list) screen sizes the app supports
# (see https://developer.android.com/guide/topics/manifest/supports-screens-element
# for all values)
# android.screens = small,normal,large,xlarge

# (list) Use this elements if you are using the experimental aapt2 toolchain
# android.aapt2 = True

#
# iOS specific
#

# (str) Path to a custom kivy-ios folder
#ios.kivy_ios_dir = ../kivy-ios
# Alternately, specify the URL and branch of a git checkout:
ios.kivy_ios_url = https://github.com/kivy/kivy-ios
#ios.kivy_ios_branch = master

# (str) Name of the certificate to use for signing the debug version
# Get a list of available identities: buildozer ios list_identities
#ios.codesign.debug = "iPhone Developer: <lastname> <firstname> (<hexstring>)"

# (str) Name of the certificate to use for signing the release version
#ios.codesign.release = %(ios.codesign.debug)s


[buildozer]

# (int) Log level (0 = error only, 1 = info, 2 = debug, 3 = trace)
log_level = 2

# (int) Display warning if buildozer is run as root (0 = False, 1 = True)
warn_on_root = 1

# (str) Path to build artifact storage, absolute or relative to spec file
# build_dir = ./.buildozer

# (str) Path to build output (i.e. .apk, .aab, .ipa)
# bin_dir = ./bin

#    -----------------------------------------------------------------------------#
#    List as sections
#
#    You can define all the "list" as [section:key].
#    Each line will be considered as a option to the list.
#    Let's take [app] / source.exclude_patterns.
#    Instead of doing:
#
#source.exclude_patterns = license,data/audio/*.wav,data/images/original/*
#
#    This can be written as:
#
#[app:source.exclude_patterns]
#license
#data/audio/*.wav
data/images/original/*

#    -----------------------------------------------------------------------------#

# (list) Pattern to include for the whole project
#[buildozer:include]
#*.py
#*.kv
#*.atlas

# (list) Pattern to exclude for the whole project
#[buildozer:exclude]
#*.pyc
#*.pyo
#*.pyd
#*__pycache__

# (list) Pattern to exclude from the zip file
#[buildozer:zipinclude]
#*.py
#*.kv
#*.atlas

# (list) Pattern to exclude from the zip file
#[buildozer:zipexclude]
#*.pyc
#*.pyo
#*.pyd
#*__pycache__
