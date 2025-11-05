# Testing Guide for Helios Frontend

This guide explains how to run and write tests for the Helios frontend.

## Test Structure

```
frontend/src/tests/
├── setup.ts              # Test setup and global mocks
├── api.test.ts           # API utility tests
└── TextDisplay.test.tsx  # Component tests
```

## Running Tests

### Install Test Dependencies

```bash
cd frontend
npm install
```

### Run All Tests

```bash
npm test
```

### Run Tests in UI Mode

```bash
npm run test:ui
```

This opens an interactive UI for running and debugging tests.

### Run Tests with Coverage

```bash
npm run test:coverage
```

View the coverage report in `coverage/index.html`.

### Watch Mode

```bash
npm test
```

By default, Vitest runs in watch mode during development.

## Test Setup

### Configuration Files

- **vitest.config.ts**: Vitest configuration
- **src/tests/setup.ts**: Global test setup and mocks

### Available Test Utilities

```typescript
import { render, screen } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import userEvent from '@testing-library/user-event';
```

## Writing Tests

### Component Tests

```typescript
import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';

describe('MyComponent', () => {
  it('renders correctly', () => {
    render(<MyComponent />);
    
    expect(screen.getByText('Hello')).toBeInTheDocument();
  });
});
```

### Testing with Router

```typescript
import { BrowserRouter } from 'react-router-dom';

const renderWithRouter = (ui: React.ReactElement) => {
  return render(<BrowserRouter>{ui}</BrowserRouter>);
};

it('navigates correctly', () => {
  renderWithRouter(<MyComponent />);
  // Test routing behavior
});
```

### Testing User Interactions

```typescript
import userEvent from '@testing-library/user-event';

it('handles click events', async () => {
  const user = userEvent.setup();
  render(<Button />);
  
  const button = screen.getByRole('button');
  await user.click(button);
  
  // Assert expected behavior
});
```

### Testing API Calls

Use MSW (Mock Service Worker) to mock API responses:

```typescript
import { setupServer } from 'msw/node';
import { http, HttpResponse } from 'msw';

const server = setupServer(
  http.get('/api/texts', () => {
    return HttpResponse.json([
      { id: 1, title: 'Iliad', author: 'Homer' }
    ]);
  })
);

beforeAll(() => server.listen());
afterEach(() => server.resetHandlers());
afterAll(() => server.close());
```

## Test Categories

### Unit Tests
- API utilities
- Helper functions
- Type definitions
- Isolated logic

### Component Tests
- Rendering
- User interactions
- Props handling
- State management

### Integration Tests
- Component interactions
- Routing
- API integration
- Full user flows

## Best Practices

1. **Test User Behavior**: Test what users see and do, not implementation details
2. **Accessible Queries**: Use `getByRole`, `getByLabelText` over `getByTestId`
3. **Async Utilities**: Use `waitFor`, `findBy` for async operations
4. **Clean Tests**: Each test should be independent
5. **Descriptive Names**: Test names should describe expected behavior
6. **Arrange-Act-Assert**: Structure tests clearly

### Good Test Example

```typescript
it('displays Greek text when user selects Iliad', async () => {
  // Arrange
  const user = userEvent.setup();
  render(<TextReader />);
  
  // Act
  const selectButton = screen.getByRole('button', { name: /select text/i });
  await user.click(selectButton);
  await user.click(screen.getByText('Iliad'));
  
  // Assert
  expect(screen.getByText(/μῆνιν/i)).toBeInTheDocument();
});
```

## Mocking

### LocalStorage

Already mocked in `setup.ts`:

```typescript
localStorage.setItem('key', 'value');
localStorage.getItem('key');
```

### Window.matchMedia

Already mocked in `setup.ts` for responsive design tests.

### External APIs

Use MSW for API mocking (preferred over jest mocks).

## Coverage Goals

- **Components**: 80%+ coverage
- **Utils/Services**: 90%+ coverage
- **Critical Paths**: 100% coverage

## Continuous Integration

Tests run automatically on:
- Push to main/develop branches
- Pull requests
- Pre-commit hooks (if configured)

## Troubleshooting

### Tests Failing Locally

1. Clear node_modules and reinstall:
```bash
rm -rf node_modules package-lock.json
npm install
```

2. Check Node version (should be 18+):
```bash
node --version
```

### Import Errors

Make sure path aliases are configured in `vitest.config.ts`:

```typescript
resolve: {
  alias: {
    '@': path.resolve(__dirname, './src'),
  },
}
```

### Component Not Rendering

Ensure all required providers are included:

```typescript
render(
  <QueryClientProvider client={queryClient}>
    <BrowserRouter>
      <MyComponent />
    </BrowserRouter>
  </QueryClientProvider>
);
```

## Resources

- [Vitest Documentation](https://vitest.dev/)
- [Testing Library](https://testing-library.com/docs/react-testing-library/intro/)
- [MSW Documentation](https://mswjs.io/)
- [Testing Best Practices](https://kentcdodds.com/blog/common-mistakes-with-react-testing-library)

## Quick Commands Reference

```bash
# Run all tests
npm test

# Run with UI
npm run test:ui

# Run with coverage
npm run test:coverage

# Run specific test file
npm test api.test.ts

# Run tests matching pattern
npm test -- --grep "API"

# Update snapshots (if using)
npm test -- -u
```

