
set(PROJECT_SRC ${CMAKE_CURRENT_SOURCE_DIR})

set(PYTHON_PREFIX ${CMAKE_SOURCE_DIR}/build/install/python-shared)
set(SSL_PREFIX ${CMAKE_SOURCE_DIR}/build/install/openssl)
set(XZ_PREFIX ${CMAKE_SOURCE_DIR}/build/install/xz)
set(BZ2_PREFIX ${CMAKE_SOURCE_DIR}/build/install/bzip2)

set(PROJ_TARGET app_shared)

add_executable(${PROJ_TARGET}
    MACOSX_BUNDLE
    ${PROJECT_SRC}/main.cpp
)

set_target_properties(${PROJ_TARGET}
    PROPERTIES
    BUNDLE True
    MACOSX_BUNDLE_GUI_IDENTIFIER org.my.${PROJ_TARGET}
    MACOSX_BUNDLE_BUNDLE_NAME ${PROJ_TARGET}
    MACOSX_BUNDLE_BUNDLE_VERSION "0.1"
    MACOSX_BUNDLE_SHORT_VERSION_STRING "0.1"
    # MACOSX_BUNDLE_INFO_PLIST ${CMAKE_SOURCE_DIR}/cmake/customtemplate.plist.in
)

target_include_directories(${PROJ_TARGET}
    PUBLIC
    ${PYTHON_PREFIX}/include/python${PYTHON_VER}
)

target_compile_options(${PROJ_TARGET}
    PUBLIC
    -fno-strict-overflow
    -Wsign-compare
    -Wunreachable-code
    -fno-common
    -dynamic
    -DNDEBUG
    -g
    -O3
    -Wall
    "-isysroot/Applications/Xcode.app/Contents/Developer/Platforms/MacOSX.platform/Developer/SDKs/MacOSX.sdk"
)

# target_link_options(${PROJ_TARGET}
#     PUBLIC
# )

target_link_directories(${PROJ_TARGET}
    PUBLIC
    ${PYTHON_PREFIX}/lib
)

target_link_libraries(${PROJ_TARGET}
    -ldl
    "-framework CoreFoundation"
    "-framework SystemConfiguration"
    -lpython${PYTHON_VER}
    ${SSL_PREFIX}/lib/libssl.a
    ${SSL_PREFIX}/lib/libcrypto.a
    ${BZ2_PREFIX}/lib/libbz2.a
    ${XZ_PREFIX}/lib/liblzma.a
    -lz
    -lsqlite3
    # -lmpdec
    -lreadline
)

# install( 
#     TARGETS ${PROJ_TARGET} 
#     BUNDLE DESTINATION ${CMAKE_BINARY_DIR}/${PROJ_TARGET}.app
# )

install(TARGETS ${PROJ_TARGET}
    BUNDLE DESTINATION . COMPONENT Runtime
    RUNTIME DESTINATION bin COMPONENT Runtime
)

# Note Mac specific extension .app
set(APPS "\${CMAKE_BINARY_DIR}/${PROJ_TARGET}.app")

# Directories to look for dependencies
set(DIRS 
    ${CMAKE_BINARY_DIR}
    ${PYTHON_PREFIX}/lib
    ${PYTHON_PREFIX}/lib/python${PYTHON_VER}/lib-dynload
)

install(CODE "include(BundleUtilities)
    fixup_bundle(\"${APPS}\" \"\" \"${DIRS}\")")

set(CPACK_GENERATOR "DRAGNDROP")
include(CPack)


