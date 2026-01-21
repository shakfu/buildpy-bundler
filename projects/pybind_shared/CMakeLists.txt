
# set(Python_ROOT_DIR build/install)

set(PROJECT_SRC ${CMAKE_CURRENT_SOURCE_DIR})

set(PYTHON_PREFIX ${CMAKE_SOURCE_DIR}/build/install/python-shared)
set(SSL_PREFIX ${CMAKE_SOURCE_DIR}/build/install/openssl)
set(XZ_PREFIX ${CMAKE_SOURCE_DIR}/build/install/xz)
set(BZ2_PREFIX ${CMAKE_SOURCE_DIR}/build/install/bzip2)

find_package(Python 3.8 COMPONENTS Interpreter Development.Module REQUIRED)

if (NOT CMAKE_BUILD_TYPE AND NOT CMAKE_CONFIGURATION_TYPES)
    set(CMAKE_BUILD_TYPE Release CACHE STRING "Choose the type of build." FORCE)
    set_property(CACHE CMAKE_BUILD_TYPE PROPERTY STRINGS "Debug" "Release" "MinSizeRel" "RelWithDebInfo")
endif()

#add_subdirectory(pybind11)
# Detect the installed nanobind package and import it into CMake

execute_process(
    COMMAND "${Python_EXECUTABLE}" -m pybind11 --cmakedir
    OUTPUT_STRIP_TRAILING_WHITESPACE OUTPUT_VARIABLE PB_DIR
)
list(APPEND CMAKE_PREFIX_PATH "${PB_DIR}")
find_package(pybind11 CONFIG REQUIRED)

add_executable(pybind_shared
    ${PROJECT_SRC}/main.cpp
)

target_include_directories(pybind_shared
    PUBLIC
    ${PYTHON_PREFIX}/include/python${PYTHON_VER}
)

target_link_directories(pybind_shared
    PUBLIC
    ${PYTHON_PREFIX}/lib
)

target_link_libraries(pybind_shared 
    pybind11::embed
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
    -lreadline
)