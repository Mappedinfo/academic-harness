// swift-tools-version: 5.9
import PackageDescription

let package = Package(
    name: "AcademicHarnessApp",
    platforms: [
        .macOS(.v13)
    ],
    products: [
        .executable(name: "AcademicHarnessApp", targets: ["AcademicHarnessApp"])
    ],
    targets: [
        .executableTarget(name: "AcademicHarnessApp")
    ]
)

