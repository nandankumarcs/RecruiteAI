/**
 * Manual test file for useResumeProgressStream hook
 * 
 * This file demonstrates how to test the hook manually.
 * To run automated tests, install @testing-library/react-hooks and vitest.
 * 
 * Example usage:
 * 
 * ```typescript
 * import { renderHook, act } from '@testing-library/react-hooks';
 * import { useResumeProgressStream } from './useResumeProgressStream';
 * 
 * // Mock EventSource
 * class MockEventSource {
 *   url: string;
 *   listeners: Map<string, Function[]> = new Map();
 *   onopen: (() => void) | null = null;
 *   onerror: (() => void) | null = null;
 *   
 *   constructor(url: string) {
 *     this.url = url;
 *     setTimeout(() => this.onopen?.(), 0);
 *   }
 *   
 *   addEventListener(event: string, handler: Function) {
 *     if (!this.listeners.has(event)) {
 *       this.listeners.set(event, []);
 *     }
 *     this.listeners.get(event)!.push(handler);
 *   }
 *   
 *   dispatchEvent(event: string, data: any) {
 *     const handlers = this.listeners.get(event) || [];
 *     handlers.forEach(handler => handler({ data: JSON.stringify(data) }));
 *   }
 *   
 *   close() {}
 * }
 * 
 * global.EventSource = MockEventSource as any;
 * 
 * test('should connect and receive events', async () => {
 *   const { result } = renderHook(() => 
 *     useResumeProgressStream('job-123', 'session-456')
 *   );
 *   
 *   expect(result.current.isConnected).toBe(false);
 *   
 *   await act(async () => {
 *     // Wait for connection
 *     await new Promise(resolve => setTimeout(resolve, 10));
 *   });
 *   
 *   expect(result.current.isConnected).toBe(true);
 * });
 * ```
 */

export {};
