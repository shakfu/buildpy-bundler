cmake_minimum_required(VERSION 3.16)
project(demo_project)

set(Python_ROOT_DIR build/install)

find_package(Python 3.8 COMPONENTS Interpreter Development.Module REQUIRED)

if (NOT Python_FOUND)
    message(FATAL_ERROR "python not found")
endif()

if (NOT CMAKE_BUILD_TYPE AND NOT CMAKE_CONFIGURATION_TYPES)
    set(CMAKE_BUILD_TYPE Release CACHE STRING "Choose the type of build." FORCE)
    set_property(CACHE CMAKE_BUILD_TYPE PROPERTY STRINGS "Debug" "Release" "MinSizeRel" "RelWithDebInfo")
endif()

message(STATUS "Python_INCLUDE_DIRS: " ${Python_INCLUDE_DIRS})
message(STATUS "Python_LINK_OPTIONS: " ${Python_LINK_OPTIONS})
message(STATUS "Python_LIBRARY_DIRS: " ${Python_LIBRARY_DIRS})
message(STATUS "Python_LIBRARIES: " ${Python_LIBRARIES})

# add_subdirectory(projects)
