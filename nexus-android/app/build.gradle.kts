import java.io.FileInputStream
import java.util.Properties

plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
}

// Release signing config (keystore.properties is gitignored; holds the keystore path + passwords).
val keystorePropsFile = rootProject.file("keystore.properties")
val keystoreProps = Properties().apply {
    if (keystorePropsFile.exists()) FileInputStream(keystorePropsFile).use { load(it) }
}

android {
    namespace = "com.mi9.nexus"
    compileSdk = 35

    signingConfigs {
        if (keystorePropsFile.exists()) {
            create("release") {
                storeFile = file(keystoreProps.getProperty("storeFile"))
                storePassword = keystoreProps.getProperty("storePassword")
                keyAlias = keystoreProps.getProperty("keyAlias")
                keyPassword = keystoreProps.getProperty("keyPassword")
            }
        }
    }

    defaultConfig {
        applicationId = "com.mi9.nexus"
        minSdk = 26
        // targetSdk 28: apps targeting API 29+ run in an SELinux domain that forbids
        // exec() from the app's private data dir (W^X). PRoot must exec the Alpine
        // binaries from filesDir, so we target 28 (the same reason Termux targets 28).
        targetSdk = 28
        versionCode = 1
        versionName = "0.1.0"

        // Local backend (llama.cpp) + tool server. 10.0.2.2 = host loopback on the
        // Android emulator; on a real device these become 127.0.0.1 once the backend
        // runs on-device (Goal 2/3).
        buildConfigField("String", "BACKEND_HOST", "\"10.0.2.2\"")
        buildConfigField("int", "BACKEND_PORT", "8080")
        buildConfigField("String", "TOOLS_HOST", "\"10.0.2.2\"")
        buildConfigField("int", "TOOLS_PORT", "8090")
    }

    buildTypes {
        release {
            isMinifyEnabled = false
            if (keystorePropsFile.exists()) {
                signingConfig = signingConfigs.getByName("release")
            }
            proguardFiles(
                getDefaultProguardFile("proguard-android-optimize.txt"),
                "proguard-rules.pro"
            )
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    kotlinOptions {
        jvmTarget = "17"
    }
    buildFeatures {
        buildConfig = true
    }

    // We ship via direct APK (not Google Play), so the Play target-SDK requirement
    // doesn't apply. targetSdk 28 is required for PRoot to exec from the app data dir.
    lint {
        disable += "ExpiredTargetSdkVersion"
    }

    // Extract native libs to nativeLibraryDir so we can exec libproot.so (proot).
    // (Modern AGP defaults to loading them straight from the APK, where exec is impossible.)
    packaging {
        jniLibs {
            useLegacyPackaging = true
            keepDebugSymbols += "**/libproot.so"
        }
    }
}

dependencies {
    // No third-party deps: pure framework WebView + a tiny asset/proxy layer.
}