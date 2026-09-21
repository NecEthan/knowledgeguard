import { httpClient, ApiError } from "@/lib/api/client";

const mockFetch = jest.fn();
global.fetch = mockFetch;

beforeEach(() => mockFetch.mockReset());

describe("httpClient", () => {
  it("returns parsed JSON on success", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve({ id: "1", email: "test@example.com" }),
    });
    const result = await httpClient("/auth/me");
    expect(result).toEqual({ id: "1", email: "test@example.com" });
  });

  it("throws ApiError with detail from response body on failure", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: false,
      status: 409,
      json: () => Promise.resolve({ detail: "Email already registered" }),
    });
    await expect(httpClient("/auth/register", { method: "POST" })).rejects.toMatchObject({
      status: 409,
      message: "Email already registered",
    });
  });

  it("throws ApiError with fallback message when response has no detail", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: false,
      status: 500,
      json: () => Promise.reject(new Error("not json")),
    });
    await expect(httpClient("/health")).rejects.toMatchObject({
      status: 500,
      message: "HTTP 500",
    });
  });

  it("throws ApiError instance", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: false,
      status: 401,
      json: () => Promise.resolve({ detail: "Unauthorized" }),
    });
    await expect(httpClient("/auth/me")).rejects.toBeInstanceOf(ApiError);
  });

  it("sends credentials: include", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve({}),
    });
    await httpClient("/auth/me");
    expect(mockFetch).toHaveBeenCalledWith(
      expect.any(String),
      expect.objectContaining({ credentials: "include" }),
    );
  });
});
