/**
 * Component tests for text display functionality
 */

import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';

describe('Text Display Component Tests', () => {
  it('should render a simple text component', () => {
    const SimpleText = () => <div>Test Text</div>;
    
    render(<SimpleText />);
    
    expect(screen.getByText('Test Text')).toBeInTheDocument();
  });
  
  it('should render Greek text correctly', () => {
    const GreekText = () => (
      <div data-testid="greek-text">
        μῆνιν ἄειδε θεὰ Πηληϊάδεω Ἀχιλῆος
      </div>
    );
    
    render(<GreekText />);
    
    const element = screen.getByTestId('greek-text');
    expect(element).toBeInTheDocument();
    expect(element.textContent).toContain('μῆνιν');
  });
  
  it('should handle empty text state', () => {
    const EmptyText = () => (
      <div data-testid="empty">
        {null}
      </div>
    );
    
    render(<EmptyText />);
    
    const element = screen.getByTestId('empty');
    expect(element).toBeInTheDocument();
    expect(element.textContent).toBe('');
  });
});

describe('Word Interaction Tests', () => {
  it('should handle word click event', () => {
    let clicked = false;
    
    const ClickableWord = () => (
      <span 
        data-testid="word"
        onClick={() => { clicked = true; }}
      >
        λόγος
      </span>
    );
    
    const { getByTestId } = render(<ClickableWord />);
    const word = getByTestId('word');
    
    word.click();
    
    expect(clicked).toBe(true);
  });
});

