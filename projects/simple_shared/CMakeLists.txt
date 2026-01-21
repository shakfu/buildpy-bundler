
set(PROJECT_SRC ${CMAKE_CURRENT_SOURCE_DIR})

set(PYTHON_PREFIX ${CMAKE_SOURCE_DIR}/build/install/python-shared)
set(SSL_PREFIX ${CMAKE_SOURCE_DIR}/build/install/openssl)
set(XZ_PREFIX ${CMAKE_SOURCE_DIR}/build/install/xz)
set(BZ2_PREFIX ${CMAKE_SOURCE_DIR}/build/install/bzip2)

add_executable(simple_shared
    ${PROJECT_SRC}/main.cpp
)

target_include_directories(simple_shared
    PUBLIC
    ${PYTHON_PREFIX}/include/python${PYTHON_VER}
)

target_compile_options(simple_shared
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

# target_link_options(simple_shared
#     PUBLIC
# )

target_link_directories(simple_shared
    PUBLIC
    ${PYTHON_PREFIX}/lib
)

target_link_libraries(simple_shared
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

