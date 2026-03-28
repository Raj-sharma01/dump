# DEVELOPMENT STANDARDS — JAVA (SPRING BOOT)

---

## RULE PRIORITY

| Tag | Meaning |
|---|---|
| `[MUST]` | Hard rule. Never violate. |
| `[MUST NOT]` | Hard prohibition. Never violate. |
| `[SHOULD]` | Strong preference. Violate only with justification. |
| `[SHOULD NOT]` | Strong discouragement. Avoid unless justified. |
| `[MAY]` | Optional. |

---

## GENERAL PRINCIPLES

```
[MUST]     Prefer readability over cleverness.
[MUST]     Write maintainable code over concise code.
[MUST]     Follow existing project patterns before introducing new ones.
[MUST NOT] Introduce abstraction without clear need.
[MUST NOT] Write dummy, demo, or placeholder code.
[MUST NOT] Leave dead or unused code.
[MUST]     Use comments only to explain WHY, never WHAT.
```

---

## NAMING CONVENTIONS

```
[MUST] Class names        → PascalCase nouns         (UserService, OrderRepository)
[MUST] Method names       → camelCase verbs           (getUserById, processOrder)
[MUST] Variable names     → camelCase                 (userRepository, orders)
[MUST] Constants          → UPPER_SNAKE_CASE           (MAX_RETRY_COUNT)
[MUST] Package names      → lowercase, no underscores (com.example.userservice)
[MUST] Test class names   → suffix with Test           (UserServiceTest)
```

**Descriptive names**

```
[MUST]     Use full, descriptive variable names.
[MUST NOT] Use abbreviations unless universally understood (DTO, API, ID, URL).
[MUST]     Name collections/lists in plural form.
```
---

## PROJECT STRUCTURE

```
[MUST] Follow layer-based architecture:
         controller   → HTTP concerns only
         service      → business logic only
         repository   → data access only
         entity       → JPA/persistence model
         dto          → API request/response shape

[MUST NOT] Put business logic in controllers.
[MUST NOT] Access repositories directly from controllers.
[MUST NOT] Expose entities in API responses.
```

---

## DEPENDENCY INJECTION

```
[MUST]       Use constructor injection exclusively.
[MUST NOT]   Use field injection (@Autowired on fields).
[SHOULD NOT] Use setter injection.
[SHOULD]     Use Lombok @RequiredArgsConstructor to generate the constructor.
             It only injects private final fields — ensure all dependencies are private final.
```
---

## CLASS DESIGN

```
[MUST]     Single Responsibility Principle — one reason to change.
[MUST]     Class length ≤ 300 lines.
[MUST]     Method length ≤ 50 lines.
[MUST]     Maximum nesting depth = 3.
[MUST NOT] Use boolean flags to control branching behavior inside a method.
[MUST]     Prefer composition over inheritance.
```

---

## OBJECT VALIDITY

```
[MUST]     All required fields must be initialized at construction time.
[MUST]     Required fields must be declared final.
[MUST NOT] Provide a public or package-private no-arg constructor.
           Exception: JPA requires a no-arg constructor — make it protected.
```

✅ GOOD — valid by construction
```java
class User {
    private final String role;

    User(String role) {
        this.role = role;
    }
}

new User("ADMIN"); // ✔ valid
```

❌ BAD — allows invalid state
```java
class User {
    private String role;

    User() {} // role = null — invalid object

    User(String role) {
        this.role = role;
    }
}

new User(); // ✔ compiles, ✘ invalid
```

**JPA exception** — if a no-arg constructor is required by the framework:

```
[SHOULD] Make it protected.
[SHOULD] Do NOT set a plausible default value. Use a clearly invalid sentinel
         so any misuse fails loudly rather than silently.
```

✅ SAFE
```java
@Entity
public class User {
    private String role;

    protected User() {
        // required by JPA — not for direct use
    }

    public User(String role) {
        this.role = role;
    }
}
```

---

## ABSTRACTION RULES

```
[MUST NOT] Create interfaces or abstract classes unless:
             - Two or more implementations exist, OR
             - A second implementation is expected imminently, OR
             - Loose coupling is explicitly required.
[MUST NOT] Create an interface for a single implementation with no justification.
[MUST]     Default to concrete classes.
```

---

## SPRING BOOT ANNOTATIONS

```
[MUST]     Use the most specific stereotype annotation available:
             @RestController  for HTTP controllers
             @Service         for business logic
             @Repository      for data access
[MUST NOT] Use @Component when a specific stereotype exists.
[MUST NOT] Use @UtilityClass for anything other than stateless utility methods.
[SHOULD]   Use Lombok (@Getter, @Setter, @Builder, @Data) to reduce boilerplate
           where it does not obscure intent.
[MUST]     Add @Override on all methods that override a superclass or interface method.

```

---

## DTO AND ENTITY

```
[MUST]     Use DTOs for all API request and response bodies.
[MUST NOT] Expose JPA entities directly in API responses.
[MUST]     Map entity ↔ DTO explicitly (manual or MapStruct).
[MUST NOT] Put business logic in DTOs.
```

---

## TRANSACTION MANAGEMENT

```
[MUST]     Apply @Transactional on service methods that perform multiple DB
           operations that must succeed or fail as a unit.
[MUST]     Mark read-only service methods with @Transactional(readOnly = true).
[MUST NOT] Place @Transactional on controller methods.
[MUST NOT] Place @Transactional on repository methods unless there is an
           explicit, documented reason.
```

✅ GOOD
```java
@Transactional
public void transferFunds(Long fromId, Long toId, BigDecimal amount) {
    accountRepository.debit(fromId, amount);
    accountRepository.credit(toId, amount);
}

@Transactional(readOnly = true)
public UserDto getUserById(Long id) { ... }
```

---

## ERROR HANDLING

```
[MUST]     Use @ControllerAdvice for global exception handling.
[MUST]     Create custom exceptions for distinct business error cases.
[MUST]     Log all handled exceptions inside GlobalExceptionHandler using SLF4J.
[MUST NOT] Expose internal exception messages or stack traces in API responses.
[MUST]     Fail fast — validate inputs at the entry point and throw immediately.
```

---

## LOGGING

```
[MUST]     Use SLF4J with Logback (Spring Boot default).
[MUST NOT] Use System.out.println or java.util.logging.
[MUST NOT] Add competing logging implementations to the classpath.
[MUST NOT] Log sensitive data (passwords, tokens, PII).

Log level guide:
  ERROR → unrecoverable failures
  WARN  → unexpected but recoverable situations
  INFO  → significant application events (startup, key flows)
  DEBUG → detailed diagnostic information (dev/staging only)
```

---

## DATABASE

```
[MUST]     Use Spring Data JPA repositories.
[MUST]     Use pagination for any query that may return unbounded results.
[MUST NOT] Encode business or domain rules inside JPQL/SQL queries.
           (Filtering and sorting by column values is acceptable;
            domain logic such as price calculations or validation is not.)
```

---

## API DESIGN

```
[MUST] Follow REST conventions.
[MUST] Use plural nouns for resource paths.
[MUST] Map HTTP methods to intent:
         GET    → read (no side effects)
         POST   → create
         PUT    → full replace
         PATCH  → partial update
         DELETE → remove
```
---

## UTILITY CLASSES

```
[MUST]     Utility class names must end with Util and reflect their responsibility
           (DateUtil, StringUtil).
[MUST]     Utility classes must contain only closely related, stateless methods.
[MUST NOT] Mix unrelated utilities in the same class.
[SHOULD]   Utility classes should have no dependencies.
```

---

## TESTING

```
[MUST]     Use JUnit 5 + Mockito.
[MUST]     Write unit tests for controllers, services, and utility classes.
[MUST]     Mock all external dependencies (repositories, HTTP clients, etc.).
[MUST NOT] Mock value objects or simple data containers.
[MUST]     Follow the existing test structure and naming conventions in the project.
[MUST]     Follow Arrange-Act-Assert structure. Separate each section with a blank line.
[MUST]     Test only one behaviour per test. The test name must describe the behaviour being     verified.
[SHOULD]   Maintain test coverage > 80%. Every public method on a service or controller must have at least one test covering the happy path and one covering the primary failure case.
```

---

## CONFIGURATION

```
[MUST]     Externalize all environment-specific configuration to properties/YAML.
[MUST NOT] Hardcode secrets, credentials, or environment-specific values in code.
[MUST]     Use Spring profiles to separate environment configuration.
```

---

## CHECKLIST — BEFORE GENERATING ANY NEW CLASS

```
[ ] SOLID principles considered
[ ] Single responsibility — one clear reason to exist
[ ] Placed in the correct layer
[ ] All dependencies injected via constructor (or @RequiredArgsConstructor)
[ ] Required fields are final
[ ] No field injection
[ ] Correct stereotype annotation used
[ ] Naming conventions followed
[ ] No business logic in controller or repository
[ ] DTOs used for all API input/output
[ ] No unnecessary abstraction introduced
[ ] No hardcoded values
[ ] No dead code
```