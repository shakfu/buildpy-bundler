
set(PROJECT_SRC ${CMAKE_CURRENT_SOURCE_DIR})

set(PYTHON_PREFIX ${CMAKE_SOURCE_DIR}/build/install/python-static)
set(SSL_PREFIX ${CMAKE_SOURCE_DIR}/build/install/openssl)
set(XZ_PREFIX ${CMAKE_SOURCE_DIR}/build/install/xz)
set(BZ2_PREFIX ${CMAKE_SOURCE_DIR}/build/install/bzip2)

message(STATUS "PYTHON_INCLUDE: " ${PYTHON_PREFIX}/include/python${PYTHON_VER})


add_executable(simple_static
    ${PROJECT_SRC}/main.cpp
)

target_include_directories(simple_static
    PUBLIC
    ${PYTHON_PREFIX}/include/python${PYTHON_VER}
)

target_compile_options(simple_static
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

# target_link_options(simple_static
#     PUBLIC
# )

target_link_directories(simple_static
    PUBLIC
    ${PYTHON_PREFIX}/lib
)

target_link_libraries(simple_static
    -ldl
    "-framework CoreFoundation"
    "-framework SystemConfiguration"
    ${PYTHON_PREFIX}/lib/libpython${PYTHON_VER}.a
    ${SSL_PREFIX}/lib/libssl.a
    ${SSL_PREFIX}/lib/libcrypto.a
    ${BZ2_PREFIX}/lib/libbz2.a
    ${XZ_PREFIX}/lib/liblzma.a
    -lz
    -lsqlite3
    # -lmpdec
    -lreadline
)

