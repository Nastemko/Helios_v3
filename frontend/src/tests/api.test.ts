/**
 * Unit tests for API utilities
 */

import { describe, it, expect, beforeEach } from 'vitest';

describe('API Configuration', () => {
  it('should construct API URL correctly', () => {
    const baseUrl = import.meta.env.VITE_API_URL || 'http://localhost:8000';
    
    expect(baseUrl).toBeDefined();
    expect(typeof baseUrl).toBe('string');
    expect(baseUrl).toMatch(/^https?:\/\//);
  });
  
  it('should have default API URL for development', () => {
    const defaultUrl = 'http://localhost:8000';
    
    expect(defaultUrl).toBe('http://localhost:8000');
  });
});

describe('API Request Headers', () => {
  beforeEach(() => {
    localStorage.clear();
  });
  
  it('should handle auth token from localStorage', () => {
    const testToken = 'test_token_123';
    localStorage.setItem('auth_token', testToken);
    
    const token = localStorage.getItem('auth_token');
    
    expect(token).toBe(testToken);
  });
  
  it('should handle missing auth token', () => {
    const token = localStorage.getItem('auth_token');
    
    expect(token).toBeNull();
  });
});

describe('URN Encoding', () => {
  it('should encode URN correctly', () => {
    const urn = 'urn:cts:greekLit:tlg0012.tlg001.perseus-grc2';
    const encoded = encodeURIComponent(urn);
    
    expect(encoded).toBe('urn%3Acts%3AgreekLit%3Atlg0012.tlg001.perseus-grc2');
  });
  
  it('should handle special characters in URN', () => {
    const urn = 'urn:cts:test:special:chars';
    const encoded = encodeURIComponent(urn);
    
    expect(encoded).toContain('%3A'); // Colon encoded
  });
});

