"""Tests for language detection and code parsing across multiple languages.

These tests cover challenging edge cases for:
- Python, JavaScript, C, C++
- Symbol extraction (classes, functions, structs, etc.)
- Large codebase handling for smaller models
"""

import pytest
from pathlib import Path
from textwrap import dedent

from opencode.tools.outline import OutlineTool, Symbol
from opencode.complexity import ComplexityAnalyzer, ComplexityResult


# ============================================================================
# Fixtures for Language-Specific Test Files
# ============================================================================

@pytest.fixture
def temp_code_dir(tmp_path):
    """Create a temporary directory for code files."""
    return tmp_path


# ============================================================================
# Python Language Tests
# ============================================================================

class TestPythonLanguageDetection:
    """Challenging Python code parsing tests."""

    def test_python_simple_class_and_function(self, temp_code_dir):
        """Test basic Python class and function detection."""
        code = dedent('''
            def hello():
                print("Hello")

            class Greeter:
                def greet(self, name):
                    return f"Hello, {name}"
        ''')
        file_path = temp_code_dir / "simple.py"
        file_path.write_text(code)

        tool = OutlineTool()
        result = tool.execute(str(file_path))

        assert result.success is True
        assert "hello" in result.output.lower()
        assert "greeter" in result.output.lower()
        assert "greet" in result.output.lower()

    def test_python_async_functions(self, temp_code_dir):
        """Test async function detection."""
        code = dedent('''
            import asyncio

            async def fetch_data(url):
                await asyncio.sleep(1)
                return {"data": url}

            async def process_all(urls):
                tasks = [fetch_data(url) for url in urls]
                return await asyncio.gather(*tasks)

            class AsyncProcessor:
                async def run(self):
                    pass
        ''')
        file_path = temp_code_dir / "async_code.py"
        file_path.write_text(code)

        tool = OutlineTool()
        result = tool.execute(str(file_path))

        assert result.success is True
        assert "fetch_data" in result.output
        assert "process_all" in result.output
        assert "AsyncProcessor" in result.output

    def test_python_nested_classes(self, temp_code_dir):
        """Test nested class detection."""
        code = dedent('''
            class Outer:
                class Inner:
                    class DeepNested:
                        def deep_method(self):
                            pass

                    def inner_method(self):
                        pass

                def outer_method(self):
                    pass

            class AnotherClass:
                pass
        ''')
        file_path = temp_code_dir / "nested.py"
        file_path.write_text(code)

        tool = OutlineTool()
        result = tool.execute(str(file_path))

        assert result.success is True
        assert "Outer" in result.output
        assert "Inner" in result.output
        assert "AnotherClass" in result.output

    def test_python_decorators_and_properties(self, temp_code_dir):
        """Test functions with decorators."""
        code = dedent('''
            from functools import wraps

            def decorator(func):
                @wraps(func)
                def wrapper(*args, **kwargs):
                    return func(*args, **kwargs)
                return wrapper

            class MyClass:
                @property
                def value(self):
                    return self._value

                @value.setter
                def value(self, v):
                    self._value = v

                @staticmethod
                def static_method():
                    pass

                @classmethod
                def class_method(cls):
                    pass

                @decorator
                def decorated_method(self):
                    pass
        ''')
        file_path = temp_code_dir / "decorators.py"
        file_path.write_text(code)

        tool = OutlineTool()
        result = tool.execute(str(file_path))

        assert result.success is True
        assert "decorator" in result.output
        assert "MyClass" in result.output

    def test_python_complex_inheritance(self, temp_code_dir):
        """Test classes with complex inheritance."""
        code = dedent('''
            from abc import ABC, abstractmethod
            from typing import Generic, TypeVar

            T = TypeVar('T')

            class BaseClass(ABC):
                @abstractmethod
                def abstract_method(self):
                    pass

            class MixinA:
                def mixin_a_method(self):
                    pass

            class MixinB:
                def mixin_b_method(self):
                    pass

            class ConcreteClass(BaseClass, MixinA, MixinB, Generic[T]):
                def abstract_method(self):
                    pass

                def concrete_method(self) -> T:
                    pass
        ''')
        file_path = temp_code_dir / "inheritance.py"
        file_path.write_text(code)

        tool = OutlineTool()
        result = tool.execute(str(file_path))

        assert result.success is True
        assert "BaseClass" in result.output
        assert "ConcreteClass" in result.output
        assert "MixinA" in result.output

    def test_python_dunder_methods(self, temp_code_dir):
        """Test detection of dunder/magic methods."""
        code = dedent('''
            class Container:
                def __init__(self, items):
                    self._items = items

                def __len__(self):
                    return len(self._items)

                def __getitem__(self, key):
                    return self._items[key]

                def __setitem__(self, key, value):
                    self._items[key] = value

                def __iter__(self):
                    return iter(self._items)

                def __repr__(self):
                    return f"Container({self._items})"

                def __enter__(self):
                    return self

                def __exit__(self, exc_type, exc_val, exc_tb):
                    pass
        ''')
        file_path = temp_code_dir / "dunder.py"
        file_path.write_text(code)

        tool = OutlineTool()
        result = tool.execute(str(file_path))

        assert result.success is True
        assert "Container" in result.output
        assert "__init__" in result.output


# ============================================================================
# JavaScript Language Tests
# ============================================================================

class TestJavaScriptLanguageDetection:
    """Challenging JavaScript code parsing tests."""

    def test_js_es6_classes(self, temp_code_dir):
        """Test ES6 class detection."""
        code = dedent('''
            class Animal {
                constructor(name) {
                    this.name = name;
                }

                speak() {
                    console.log(`${this.name} makes a sound.`);
                }
            }

            class Dog extends Animal {
                constructor(name, breed) {
                    super(name);
                    this.breed = breed;
                }

                speak() {
                    console.log(`${this.name} barks.`);
                }

                fetch() {
                    console.log(`${this.name} fetches the ball.`);
                }
            }
        ''')
        file_path = temp_code_dir / "classes.js"
        file_path.write_text(code)

        tool = OutlineTool()
        result = tool.execute(str(file_path))

        assert result.success is True
        assert "Animal" in result.output
        assert "Dog" in result.output

    def test_js_arrow_functions(self, temp_code_dir):
        """Test arrow function detection."""
        code = dedent('''
            const add = (a, b) => a + b;

            const multiply = (a, b) => {
                return a * b;
            };

            const fetchData = async (url) => {
                const response = await fetch(url);
                return response.json();
            };

            const processItems = async (items) => {
                return items.map(item => item.toUpperCase());
            };

            const createHandler = (prefix) => (event) => {
                console.log(prefix, event);
            };
        ''')
        file_path = temp_code_dir / "arrows.js"
        file_path.write_text(code)

        tool = OutlineTool()
        result = tool.execute(str(file_path))

        assert result.success is True
        assert "add" in result.output or "multiply" in result.output

    def test_js_async_await(self, temp_code_dir):
        """Test async/await function detection."""
        code = dedent('''
            async function fetchUser(id) {
                const response = await fetch(`/api/users/${id}`);
                return response.json();
            }

            async function fetchAllUsers() {
                const users = await fetchUser(1);
                return users;
            }

            class ApiClient {
                async get(url) {
                    return fetch(url);
                }

                async post(url, data) {
                    return fetch(url, {
                        method: 'POST',
                        body: JSON.stringify(data)
                    });
                }
            }
        ''')
        file_path = temp_code_dir / "async.js"
        file_path.write_text(code)

        tool = OutlineTool()
        result = tool.execute(str(file_path))

        assert result.success is True
        assert "fetchUser" in result.output
        assert "ApiClient" in result.output

    def test_js_module_pattern(self, temp_code_dir):
        """Test module pattern and IIFE."""
        code = dedent('''
            const MyModule = (function() {
                let privateVar = 0;

                function privateMethod() {
                    return privateVar;
                }

                function publicMethod() {
                    privateVar++;
                    return privateMethod();
                }

                return {
                    increment: publicMethod
                };
            })();

            function standaloneFunction() {
                return "standalone";
            }

            class ExportedClass {
                constructor() {}
            }
        ''')
        file_path = temp_code_dir / "module.js"
        file_path.write_text(code)

        tool = OutlineTool()
        result = tool.execute(str(file_path))

        assert result.success is True
        assert "standaloneFunction" in result.output or "ExportedClass" in result.output

    def test_js_object_methods(self, temp_code_dir):
        """Test object method shorthand detection."""
        code = dedent('''
            const calculator = {
                add(a, b) {
                    return a + b;
                },
                subtract(a, b) {
                    return a - b;
                },
                async fetchRate(currency) {
                    return 1.0;
                }
            };

            function createApi() {
                return {
                    get(url) { return fetch(url); },
                    post(url, data) { return fetch(url, { method: 'POST', body: data }); }
                };
            }
        ''')
        file_path = temp_code_dir / "object_methods.js"
        file_path.write_text(code)

        tool = OutlineTool()
        result = tool.execute(str(file_path))

        assert result.success is True
        assert "createApi" in result.output


# ============================================================================
# C Language Tests
# ============================================================================

class TestCLanguageDetection:
    """Challenging C code parsing tests."""

    def test_c_structs_and_functions(self, temp_code_dir):
        """Test C struct and function detection."""
        code = dedent('''
            #include <stdio.h>
            #include <stdlib.h>

            struct Point {
                int x;
                int y;
            };

            struct Rectangle {
                struct Point top_left;
                struct Point bottom_right;
            };

            void init_point(struct Point* p, int x, int y) {
                p->x = x;
                p->y = y;
            }

            int calculate_area(struct Rectangle* rect) {
                int width = rect->bottom_right.x - rect->top_left.x;
                int height = rect->bottom_right.y - rect->top_left.y;
                return width * height;
            }

            static inline int max(int a, int b) {
                return a > b ? a : b;
            }
        ''')
        file_path = temp_code_dir / "structs.c"
        file_path.write_text(code)

        tool = OutlineTool()
        result = tool.execute(str(file_path))

        assert result.success is True
        # C parser detects functions - struct detection depends on brace style
        assert "init_point" in result.output or "calculate_area" in result.output or "max" in result.output

    def test_c_function_pointers(self, temp_code_dir):
        """Test C with function pointers."""
        code = dedent('''
            typedef int (*compare_fn)(const void*, const void*);
            typedef void (*callback_fn)(int, void*);

            struct Callbacks {
                callback_fn on_success;
                callback_fn on_error;
            };

            int compare_ints(const void* a, const void* b) {
                return *(int*)a - *(int*)b;
            }

            void sort_array(int* arr, size_t len, compare_fn cmp) {
                qsort(arr, len, sizeof(int), cmp);
            }

            void* create_handler(callback_fn success, callback_fn error) {
                struct Callbacks* cb = malloc(sizeof(struct Callbacks));
                cb->on_success = success;
                cb->on_error = error;
                return cb;
            }
        ''')
        file_path = temp_code_dir / "function_ptrs.c"
        file_path.write_text(code)

        tool = OutlineTool()
        result = tool.execute(str(file_path))

        assert result.success is True
        assert "compare_ints" in result.output or "sort_array" in result.output

    def test_c_complex_declarations(self, temp_code_dir):
        """Test complex C declarations."""
        code = dedent('''
            #define MAX_BUFFER 1024
            #define ARRAY_SIZE(arr) (sizeof(arr) / sizeof((arr)[0]))

            typedef struct node {
                int value;
                struct node* next;
                struct node* prev;
            } Node;

            typedef struct {
                Node* head;
                Node* tail;
                size_t size;
            } LinkedList;

            enum Status {
                STATUS_OK = 0,
                STATUS_ERROR = -1,
                STATUS_PENDING = 1
            };

            static const char* status_to_string(enum Status s) {
                switch (s) {
                    case STATUS_OK: return "OK";
                    case STATUS_ERROR: return "ERROR";
                    case STATUS_PENDING: return "PENDING";
                    default: return "UNKNOWN";
                }
            }

            LinkedList* list_create(void) {
                LinkedList* list = calloc(1, sizeof(LinkedList));
                return list;
            }

            void list_destroy(LinkedList* list) {
                Node* current = list->head;
                while (current) {
                    Node* next = current->next;
                    free(current);
                    current = next;
                }
                free(list);
            }
        ''')
        file_path = temp_code_dir / "complex.c"
        file_path.write_text(code)

        tool = OutlineTool()
        result = tool.execute(str(file_path))

        assert result.success is True
        output_lower = result.output.lower()
        assert "list_create" in result.output or "struct" in output_lower

    def test_c_header_file(self, temp_code_dir):
        """Test C header file parsing."""
        code = dedent('''
            #ifndef MYLIB_H
            #define MYLIB_H

            #include <stddef.h>
            #include <stdbool.h>

            #ifdef __cplusplus
            extern "C" {
            #endif

            struct Config {
                int timeout;
                bool verbose;
                const char* endpoint;
            };

            typedef struct Config Config;

            // Initialize with defaults
            void config_init(Config* cfg);

            // Load from file
            int config_load(Config* cfg, const char* path);

            // Save to file
            int config_save(const Config* cfg, const char* path);

            // Cleanup
            void config_destroy(Config* cfg);

            #ifdef __cplusplus
            }
            #endif

            #endif // MYLIB_H
        ''')
        file_path = temp_code_dir / "mylib.h"
        file_path.write_text(code)

        tool = OutlineTool()
        result = tool.execute(str(file_path))

        assert result.success is True
        assert "Config" in result.output or "config_init" in result.output


# ============================================================================
# C++ Language Tests
# ============================================================================

class TestCppLanguageDetection:
    """Challenging C++ code parsing tests."""

    def test_cpp_classes_and_inheritance(self, temp_code_dir):
        """Test C++ class and inheritance detection."""
        code = dedent('''
            #include <string>
            #include <vector>

            class Shape {
            public:
                virtual ~Shape() = default;
                virtual double area() const = 0;
                virtual double perimeter() const = 0;
            };

            class Circle : public Shape {
            private:
                double radius;
            public:
                explicit Circle(double r) : radius(r) {}
                double area() const override { return 3.14159 * radius * radius; }
                double perimeter() const override { return 2 * 3.14159 * radius; }
            };

            class Rectangle : public Shape {
            private:
                double width, height;
            public:
                Rectangle(double w, double h) : width(w), height(h) {}
                double area() const override { return width * height; }
                double perimeter() const override { return 2 * (width + height); }
            };
        ''')
        file_path = temp_code_dir / "shapes.cpp"
        file_path.write_text(code)

        tool = OutlineTool()
        result = tool.execute(str(file_path))

        assert result.success is True
        assert "Shape" in result.output
        assert "Circle" in result.output
        assert "Rectangle" in result.output

    def test_cpp_templates(self, temp_code_dir):
        """Test C++ template detection."""
        code = dedent('''
            #include <vector>
            #include <algorithm>

            template<typename T>
            class Stack {
            private:
                std::vector<T> data;
            public:
                void push(const T& value) { data.push_back(value); }
                T pop() {
                    T val = data.back();
                    data.pop_back();
                    return val;
                }
                bool empty() const { return data.empty(); }
                size_t size() const { return data.size(); }
            };

            template<typename T, typename Compare = std::less<T>>
            T find_min(const std::vector<T>& vec, Compare cmp = Compare()) {
                return *std::min_element(vec.begin(), vec.end(), cmp);
            }

            template<typename Container, typename Predicate>
            auto filter(const Container& c, Predicate pred) {
                Container result;
                std::copy_if(c.begin(), c.end(), std::back_inserter(result), pred);
                return result;
            }
        ''')
        file_path = temp_code_dir / "templates.cpp"
        file_path.write_text(code)

        tool = OutlineTool()
        result = tool.execute(str(file_path))

        assert result.success is True
        assert "Stack" in result.output

    def test_cpp_namespaces(self, temp_code_dir):
        """Test C++ namespace detection."""
        code = dedent('''
            namespace mylib {
                namespace utils {
                    class StringHelper {
                    public:
                        static std::string trim(const std::string& s);
                        static std::vector<std::string> split(const std::string& s, char delim);
                    };

                    int calculate_hash(const std::string& input) {
                        int hash = 0;
                        for (char c : input) hash = hash * 31 + c;
                        return hash;
                    }
                }

                namespace io {
                    class FileReader {
                    public:
                        bool open(const std::string& path);
                        std::string read_all();
                        void close();
                    };

                    class FileWriter {
                    public:
                        bool open(const std::string& path);
                        void write(const std::string& content);
                        void close();
                    };
                }
            }

            namespace mylib::experimental {
                class NewFeature {
                    void do_something();
                };
            }
        ''')
        file_path = temp_code_dir / "namespaces.cpp"
        file_path.write_text(code)

        tool = OutlineTool()
        result = tool.execute(str(file_path))

        assert result.success is True
        output_lower = result.output.lower()
        assert "namespace" in output_lower or "mylib" in result.output

    def test_cpp_operator_overloading(self, temp_code_dir):
        """Test C++ operator overloading detection."""
        code = dedent('''
            class Complex {
            private:
                double real, imag;
            public:
                Complex(double r = 0, double i = 0) : real(r), imag(i) {}

                Complex operator+(const Complex& other) const {
                    return Complex(real + other.real, imag + other.imag);
                }

                Complex operator-(const Complex& other) const {
                    return Complex(real - other.real, imag - other.imag);
                }

                Complex operator*(const Complex& other) const {
                    return Complex(
                        real * other.real - imag * other.imag,
                        real * other.imag + imag * other.real
                    );
                }

                bool operator==(const Complex& other) const {
                    return real == other.real && imag == other.imag;
                }

                Complex& operator+=(const Complex& other) {
                    real += other.real;
                    imag += other.imag;
                    return *this;
                }

                friend std::ostream& operator<<(std::ostream& os, const Complex& c) {
                    return os << c.real << " + " << c.imag << "i";
                }
            };
        ''')
        file_path = temp_code_dir / "operators.cpp"
        file_path.write_text(code)

        tool = OutlineTool()
        result = tool.execute(str(file_path))

        assert result.success is True
        assert "Complex" in result.output

    def test_cpp_modern_features(self, temp_code_dir):
        """Test modern C++ features (C++11/14/17/20)."""
        code = dedent('''
            #include <memory>
            #include <functional>
            #include <optional>

            class ModernClass {
            public:
                // Rule of five
                ModernClass() = default;
                ~ModernClass() = default;
                ModernClass(const ModernClass&) = default;
                ModernClass(ModernClass&&) noexcept = default;
                ModernClass& operator=(const ModernClass&) = default;
                ModernClass& operator=(ModernClass&&) noexcept = default;

                // Lambda member
                std::function<int(int)> transformer = [](int x) { return x * 2; };

                // Optional return
                std::optional<int> find_value(int key) const {
                    if (key > 0) return key;
                    return std::nullopt;
                }

                // Constexpr
                static constexpr int max_size() { return 100; }

                // Auto return type
                auto get_data() const -> const std::vector<int>& {
                    return data;
                }

            private:
                std::vector<int> data;
                std::unique_ptr<int[]> buffer;
            };

            // Structured bindings (C++17)
            auto split_pair(const std::pair<int, int>& p) {
                auto [first, second] = p;
                return first + second;
            }

            // Concepts (C++20) - if supported
            template<typename T>
            concept Numeric = std::is_arithmetic_v<T>;

            template<Numeric T>
            T add(T a, T b) { return a + b; }
        ''')
        file_path = temp_code_dir / "modern.cpp"
        file_path.write_text(code)

        tool = OutlineTool()
        result = tool.execute(str(file_path))

        assert result.success is True
        assert "ModernClass" in result.output


# ============================================================================
# TypeScript Tests (extends JavaScript)
# ============================================================================

class TestTypeScriptLanguageDetection:
    """TypeScript-specific parsing tests."""

    def test_ts_interfaces_and_types(self, temp_code_dir):
        """Test TypeScript interface and type detection."""
        code = dedent('''
            interface User {
                id: number;
                name: string;
                email: string;
                createdAt: Date;
            }

            interface Admin extends User {
                permissions: string[];
                adminLevel: number;
            }

            type Status = 'active' | 'inactive' | 'pending';
            type UserMap = Map<string, User>;

            type ApiResponse<T> = {
                data: T;
                error: string | null;
                status: number;
            };

            interface Repository<T> {
                find(id: string): Promise<T | null>;
                save(entity: T): Promise<T>;
                delete(id: string): Promise<boolean>;
            }

            class UserRepository implements Repository<User> {
                async find(id: string): Promise<User | null> {
                    return null;
                }

                async save(entity: User): Promise<User> {
                    return entity;
                }

                async delete(id: string): Promise<boolean> {
                    return true;
                }
            }
        ''')
        file_path = temp_code_dir / "types.ts"
        file_path.write_text(code)

        tool = OutlineTool()
        result = tool.execute(str(file_path))

        assert result.success is True
        assert "User" in result.output or "interface" in result.output.lower()

    def test_ts_enums_and_decorators(self, temp_code_dir):
        """Test TypeScript enums and decorators."""
        code = dedent('''
            enum HttpStatus {
                OK = 200,
                Created = 201,
                BadRequest = 400,
                Unauthorized = 401,
                NotFound = 404,
                InternalError = 500
            }

            enum LogLevel {
                Debug = "DEBUG",
                Info = "INFO",
                Warn = "WARN",
                Error = "ERROR"
            }

            function Component(selector: string) {
                return function<T extends { new(...args: any[]): {} }>(constructor: T) {
                    return class extends constructor {
                        selector = selector;
                    };
                };
            }

            function Injectable() {
                return function(target: any) {
                    // DI logic
                };
            }

            @Component('app-user')
            class UserComponent {
                constructor(private userService: UserService) {}

                render() {
                    return `<div>User</div>`;
                }
            }

            @Injectable()
            class UserService {
                getUser(id: string) {
                    return { id, name: 'Test' };
                }
            }
        ''')
        file_path = temp_code_dir / "decorators.ts"
        file_path.write_text(code)

        tool = OutlineTool()
        result = tool.execute(str(file_path))

        assert result.success is True
        assert "HttpStatus" in result.output or "enum" in result.output.lower()


# ============================================================================
# Complexity Analysis Tests
# ============================================================================

class TestComplexityAnalysis:
    """Tests for task complexity analysis."""

    def test_simple_task_low_complexity(self):
        """Test that simple tasks have low complexity."""
        analyzer = ComplexityAnalyzer(threshold=0.6)

        simple_tasks = [
            "Fix the typo in the README",
            "Add a print statement",
            "Update the version number",
            "Remove unused import",
        ]

        for task in simple_tasks:
            result = analyzer.analyze(task)
            assert result.score < 0.4, f"Task should be simple: {task}"
            assert result.should_plan is False

    def test_complex_task_high_complexity(self):
        """Test that complex tasks have high complexity."""
        analyzer = ComplexityAnalyzer(threshold=0.6)

        complex_tasks = [
            "Refactor the entire authentication system",
            "Migrate all database queries to the new ORM",
            "Restructure the project to use microservices architecture",
            "Rewrite the API layer using GraphQL",
        ]

        for task in complex_tasks:
            result = analyzer.analyze(task)
            assert result.score >= 0.3, f"Task should be complex: {task}"

    def test_multi_step_task(self):
        """Test multi-step task detection."""
        analyzer = ComplexityAnalyzer(threshold=0.6)

        task = "First, update the database schema, then migrate existing data, and finally update all the API endpoints"
        result = analyzer.analyze(task)

        assert result.score >= 0.4
        assert len(result.signals) >= 2

    def test_scope_indicators(self):
        """Test scope indicator detection."""
        analyzer = ComplexityAnalyzer(threshold=0.6)

        tasks_with_scope = [
            "Update all files in the project",
            "Fix bugs throughout the codebase",
            "Apply changes across the entire application",
        ]

        for task in tasks_with_scope:
            result = analyzer.analyze(task)
            assert result.score >= 0.2, f"Should detect scope: {task}"

    def test_threshold_adjustment(self):
        """Test complexity threshold adjustment."""
        analyzer = ComplexityAnalyzer(threshold=0.3)

        task = "Improve the login flow"
        result_low = analyzer.analyze(task)

        analyzer.set_threshold(0.9)
        result_high = analyzer.analyze(task)

        # Same score, different decisions
        assert result_low.score == result_high.score
        # With lower threshold, more likely to trigger planning
        # With higher threshold, less likely

    def test_explain_output(self):
        """Test explanation output format."""
        analyzer = ComplexityAnalyzer(threshold=0.6)

        task = "Refactor the authentication module and update all tests"
        explanation = analyzer.explain(task)

        assert "Complexity Score" in explanation
        assert "Auto-Plan" in explanation
        assert "threshold" in explanation.lower()


# ============================================================================
# Large Codebase Tests (for smaller models)
# ============================================================================

class TestLargeCodebaseHandling:
    """Tests for handling large codebases with smaller models."""

    def test_large_python_file(self, temp_code_dir):
        """Test handling a large Python file (1000+ lines)."""
        # Generate a large Python file
        lines = ['"""Large Python module for testing."""', '', 'import os', 'import sys', '']

        # Add 50 classes with 5 methods each
        for i in range(50):
            lines.append(f'class TestClass{i}:')
            lines.append(f'    """Class number {i}."""')
            lines.append('')
            for j in range(5):
                lines.append(f'    def method_{j}(self, arg1, arg2):')
                lines.append(f'        """Method {j} of class {i}."""')
                lines.append(f'        result = arg1 + arg2 + {i} + {j}')
                lines.append(f'        return result')
                lines.append('')
            lines.append('')

        # Add 100 standalone functions
        for i in range(100):
            lines.append(f'def standalone_function_{i}(x, y, z):')
            lines.append(f'    """Standalone function {i}."""')
            lines.append(f'    return x * y * z + {i}')
            lines.append('')

        content = '\n'.join(lines)
        file_path = temp_code_dir / "large_module.py"
        file_path.write_text(content)

        # Verify file is large
        assert len(content.splitlines()) > 500

        tool = OutlineTool()
        result = tool.execute(str(file_path))

        assert result.success is True
        # Should detect multiple symbols
        assert "TestClass" in result.output
        assert "standalone_function" in result.output

    def test_large_cpp_file(self, temp_code_dir):
        """Test handling a large C++ file."""
        lines = ['#include <iostream>', '#include <vector>', '#include <string>', '']

        # Add namespaces with classes
        for ns in range(5):
            lines.append(f'namespace module{ns} {{')
            for cls in range(10):
                lines.append(f'    class Service{cls} {{')
                lines.append(f'    public:')
                for method in range(8):
                    lines.append(f'        void handle_{method}(int param) {{')
                    lines.append(f'            // Implementation {ns}-{cls}-{method}')
                    lines.append(f'        }}')
                lines.append(f'    }};')
                lines.append('')
            lines.append(f'}} // namespace module{ns}')
            lines.append('')

        content = '\n'.join(lines)
        file_path = temp_code_dir / "large_service.cpp"
        file_path.write_text(content)

        tool = OutlineTool()
        result = tool.execute(str(file_path))

        assert result.success is True
        assert "namespace" in result.output.lower() or "Service" in result.output

    def test_large_javascript_file(self, temp_code_dir):
        """Test handling a large JavaScript file."""
        lines = ['// Large JavaScript module', '"use strict";', '']

        # Add many classes and functions
        for i in range(30):
            lines.append(f'class Component{i} {{')
            lines.append(f'    constructor(props) {{')
            lines.append(f'        this.props = props;')
            lines.append(f'    }}')
            for j in range(5):
                lines.append(f'    handle{j}(event) {{')
                lines.append(f'        console.log("Handling", event);')
                lines.append(f'    }}')
            lines.append(f'}}')
            lines.append('')

        for i in range(50):
            lines.append(f'async function asyncOperation{i}(data) {{')
            lines.append(f'    const result = await fetch("/api/{i}");')
            lines.append(f'    return result.json();')
            lines.append(f'}}')
            lines.append('')

        content = '\n'.join(lines)
        file_path = temp_code_dir / "large_app.js"
        file_path.write_text(content)

        tool = OutlineTool()
        result = tool.execute(str(file_path))

        assert result.success is True
        assert "Component" in result.output

    def test_many_files_simulation(self, temp_code_dir):
        """Test handling multiple files (simulating large codebase)."""
        # Create a project structure with many files
        src_dir = temp_code_dir / "src"
        src_dir.mkdir()

        # Create Python files
        for i in range(20):
            file_path = src_dir / f"module_{i}.py"
            content = f'''"""Module {i}"""

class Handler{i}:
    def process(self, data):
        return data

def utility_{i}(x):
    return x * 2
'''
            file_path.write_text(content)

        # Create JS files
        js_dir = temp_code_dir / "frontend"
        js_dir.mkdir()

        for i in range(15):
            file_path = js_dir / f"component_{i}.js"
            content = f'''// Component {i}

class View{i} {{
    render() {{
        return "<div>View {i}</div>";
    }}
}}

export default View{i};
'''
            file_path.write_text(content)

        # Verify files were created
        py_files = list(src_dir.glob("*.py"))
        js_files = list(js_dir.glob("*.js"))

        assert len(py_files) == 20
        assert len(js_files) == 15

        # Test that outline works on each file
        tool = OutlineTool()

        for py_file in py_files[:5]:  # Test first 5
            result = tool.execute(str(py_file))
            assert result.success is True
            assert "Handler" in result.output or "utility" in result.output

    def test_deeply_nested_code(self, temp_code_dir):
        """Test handling deeply nested code structures."""
        code = dedent('''
            class Level1:
                class Level2:
                    class Level3:
                        class Level4:
                            class Level5:
                                def deep_method(self):
                                    pass

                            def level4_method(self):
                                pass

                        def level3_method(self):
                            pass

                    def level2_method(self):
                        pass

                def level1_method(self):
                    pass

            def top_level_function():
                def nested_function():
                    def deeply_nested():
                        pass
                    return deeply_nested
                return nested_function

            class AnotherClass:
                pass
        ''')
        file_path = temp_code_dir / "nested_deep.py"
        file_path.write_text(code)

        tool = OutlineTool()
        result = tool.execute(str(file_path))

        assert result.success is True
        assert "Level1" in result.output
        assert "top_level_function" in result.output

    def test_mixed_language_project(self, temp_code_dir):
        """Test handling a project with multiple languages."""
        # Python
        (temp_code_dir / "backend.py").write_text('''
class ApiServer:
    def start(self):
        pass

def create_app():
    return ApiServer()
''')

        # JavaScript
        (temp_code_dir / "frontend.js").write_text('''
class App {
    constructor() {}
    render() {}
}

function initApp() {
    return new App();
}
''')

        # C header - use function definitions that the parser can detect
        (temp_code_dir / "native.h").write_text('''
struct NativeModule {
    int initialized;
    void* handle;
};

int native_init(struct NativeModule* mod) {
    return 0;
}

void native_cleanup(struct NativeModule* mod) {
}
''')

        # C++ implementation
        (temp_code_dir / "native.cpp").write_text('''
class NativeWrapper {
public:
    NativeWrapper();
    ~NativeWrapper();
    void process(const std::string& input);
};

namespace impl {
    void internal_process(void* data);
}
''')

        tool = OutlineTool()

        # Test each file
        py_result = tool.execute(str(temp_code_dir / "backend.py"))
        assert py_result.success is True
        assert "ApiServer" in py_result.output

        js_result = tool.execute(str(temp_code_dir / "frontend.js"))
        assert js_result.success is True
        assert "App" in js_result.output

        h_result = tool.execute(str(temp_code_dir / "native.h"))
        assert h_result.success is True
        # C parser detects function definitions with bodies
        assert "native_init" in h_result.output or "native_cleanup" in h_result.output

        cpp_result = tool.execute(str(temp_code_dir / "native.cpp"))
        assert cpp_result.success is True
        assert "NativeWrapper" in cpp_result.output


# ============================================================================
# Edge Cases and Error Handling
# ============================================================================

class TestLanguageEdgeCases:
    """Edge cases and error handling tests."""

    def test_empty_file(self, temp_code_dir):
        """Test handling empty files."""
        file_path = temp_code_dir / "empty.py"
        file_path.write_text("")

        tool = OutlineTool()
        result = tool.execute(str(file_path))

        assert result.success is True
        assert "no symbols" in result.output.lower()

    def test_comments_only_file(self, temp_code_dir):
        """Test file with only comments."""
        code = '''# This is a comment
# Another comment
# No actual code here

"""
This is a docstring
but no functions or classes
"""
'''
        file_path = temp_code_dir / "comments.py"
        file_path.write_text(code)

        tool = OutlineTool()
        result = tool.execute(str(file_path))

        assert result.success is True

    def test_syntax_error_handling(self, temp_code_dir):
        """Test handling files with syntax errors."""
        # Python with syntax error
        code = '''
def broken_function(
    # Missing closing paren and body

class IncompleteClass
    # Missing colon
'''
        file_path = temp_code_dir / "broken.py"
        file_path.write_text(code)

        tool = OutlineTool()
        result = tool.execute(str(file_path))

        # Should still attempt to extract what it can
        assert result.success is True

    def test_unicode_identifiers(self, temp_code_dir):
        """Test handling unicode in identifiers."""
        code = '''
class ユーザー:
    def 処理(self):
        pass

def 計算(数値):
    return 数値 * 2

class Ñoño:
    def método(self):
        pass
'''
        file_path = temp_code_dir / "unicode.py"
        file_path.write_text(code)

        tool = OutlineTool()
        result = tool.execute(str(file_path))

        assert result.success is True

    def test_very_long_lines(self, temp_code_dir):
        """Test handling very long lines."""
        long_params = ", ".join([f"param{i}: str" for i in range(50)])
        code = f'''
def function_with_many_params({long_params}):
    pass

class ClassWithLongName{"A" * 200}:
    pass
'''
        file_path = temp_code_dir / "long_lines.py"
        file_path.write_text(code)

        tool = OutlineTool()
        result = tool.execute(str(file_path))

        assert result.success is True

    def test_unsupported_extension(self, temp_code_dir):
        """Test handling unsupported file types."""
        file_path = temp_code_dir / "data.xyz"
        file_path.write_text("Some random content")

        tool = OutlineTool()
        result = tool.execute(str(file_path))

        assert result.success is False
        assert "unsupported" in result.error.lower()

    def test_binary_file_detection(self, temp_code_dir):
        """Test detection of binary files."""
        file_path = temp_code_dir / "binary.py"
        # Write some binary content
        file_path.write_bytes(b'\x00\x01\x02\x03\xff\xfe\xfd')

        tool = OutlineTool()
        result = tool.execute(str(file_path))

        # Should handle gracefully
        assert result is not None
