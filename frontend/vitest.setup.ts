import "@testing-library/jest-dom/vitest";

// jsdom doesn't implement ResizeObserver, which Recharts' <ResponsiveContainer>
// relies on to measure its parent and size the chart. Provide a minimal stub
// plus non-zero element dimensions so charts actually render their children
// during tests instead of silently producing an empty container.
const CHART_WIDTH = 600;
const CHART_HEIGHT = 400;

class ResizeObserverStub {
    private callback: ResizeObserverCallback;
    constructor(callback: ResizeObserverCallback) {
        this.callback = callback;
    }
    observe(target: Element) {
        // Recharts' <ResponsiveContainer> sizes itself off the first
        // ResizeObserver callback. jsdom never fires real resize events, so
        // invoke it once synchronously with the stubbed dimensions below.
        this.callback(
            [
                {
                    target,
                    contentRect: { width: CHART_WIDTH, height: CHART_HEIGHT } as DOMRectReadOnly,
                } as ResizeObserverEntry,
            ],
            this as unknown as ResizeObserver
        );
    }
    unobserve() {}
    disconnect() {}
}

// jsdom's runtime has no ResizeObserver at all (lib.dom.d.ts merely declares
// the browser type), so always install the stub.
globalThis.ResizeObserver = ResizeObserverStub as unknown as typeof ResizeObserver;

Object.defineProperty(HTMLElement.prototype, "offsetWidth", {
    configurable: true,
    value: CHART_WIDTH,
});
Object.defineProperty(HTMLElement.prototype, "offsetHeight", {
    configurable: true,
    value: CHART_HEIGHT,
});
HTMLElement.prototype.getBoundingClientRect = function () {
    return {
        width: CHART_WIDTH,
        height: CHART_HEIGHT,
        top: 0,
        left: 0,
        bottom: CHART_HEIGHT,
        right: CHART_WIDTH,
        x: 0,
        y: 0,
        toJSON() {},
    } as DOMRect;
};
