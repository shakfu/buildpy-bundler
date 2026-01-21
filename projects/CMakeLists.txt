
# set(CMAKE_ARCHIVE_OUTPUT_DIRECTORY ${CMAKE_BINARY_DIR}/lib)
# set(CMAKE_LIBRARY_OUTPUT_DIRECTORY ${CMAKE_BINARY_DIR}/lib)
set(CMAKE_RUNTIME_OUTPUT_DIRECTORY ${CMAKE_BINARY_DIR})

# assume python-static exists
if (EXISTS ${CMAKE_SOURCE_DIR}/build/install/python-static)
    set(PYTHON_PREFIX ${CMAKE_SOURCE_DIR}/build/install/python-static)

    execute_process(
        COMMAND "${PYTHON_PREFIX}/bin/python3" -c "import sysconfig; print(sysconfig.get_python_version())"
        OUTPUT_STRIP_TRAILING_WHITESPACE OUTPUT_VARIABLE PYTHON_VER
    )

    if (DEFINED PYTHON_VER)
        add_subdirectory(simple_static)
        add_subdirectory(pybind_static)
    endif()
endif()

# assume python-shared exists
if (EXISTS ${CMAKE_SOURCE_DIR}/build/install/python-shared)
    set(PYTHON_PREFIX ${CMAKE_SOURCE_DIR}/build/install/python-shared)

    execute_process(
        COMMAND "${PYTHON_PREFIX}/bin/python3" -c "import sysconfig; print(sysconfig.get_python_version())"
        OUTPUT_STRIP_TRAILING_WHITESPACE OUTPUT_VARIABLE PYTHON_VER
    )

    if (DEFINED PYTHON_VER)
        add_subdirectory(app_shared)
        add_subdirectory(simple_shared)
        add_subdirectory(pybind_shared)
    endif()
endif()
