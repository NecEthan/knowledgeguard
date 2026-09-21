import { ApiError } from "@/lib/api/client";
import { deleteDocument, listDocuments, uploadDocument } from "@/lib/api/documents";

const mockFetch = jest.fn();
global.fetch = mockFetch;

beforeEach(() => mockFetch.mockReset());

describe("uploadDocument", () => {
  it("sends POST with FormData containing file and title", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve({ id: "uuid-1", status: "accepted" }),
    });

    const file = new File(["hello"], "test.txt", { type: "text/plain" });
    const result = await uploadDocument(file, "My Doc");

    expect(result).toEqual({ id: "uuid-1", status: "accepted" });
    const [url, opts] = mockFetch.mock.calls[0] as [string, RequestInit];
    expect(url).toContain("/documents");
    expect(opts.method).toBe("POST");
    expect(opts.credentials).toBe("include");
    expect(opts.body).toBeInstanceOf(FormData);
  });

  it("throws ApiError with backend detail on failure", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: false,
      status: 413,
      json: () => Promise.resolve({ detail: "File exceeds 50 MB limit" }),
    });

    const file = new File(["x"], "big.txt");
    await expect(uploadDocument(file, "title")).rejects.toMatchObject({
      status: 413,
      message: "File exceeds 50 MB limit",
    });
  });

  it("throws ApiError instance on failure", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: false,
      status: 415,
      json: () => Promise.resolve({ detail: "Unsupported file type" }),
    });

    await expect(uploadDocument(new File([""], "f.exe"), "t")).rejects.toBeInstanceOf(ApiError);
  });
});

describe("deleteDocument", () => {
  it("sends DELETE request to correct URL", async () => {
    mockFetch.mockResolvedValueOnce({ ok: true });

    await deleteDocument("doc-abc");

    const [url, opts] = mockFetch.mock.calls[0] as [string, RequestInit];
    expect(url).toContain("/documents/doc-abc");
    expect(opts.method).toBe("DELETE");
    expect(opts.credentials).toBe("include");
  });

  it("throws ApiError on failure", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: false,
      status: 404,
      json: () => Promise.resolve({ detail: "Document not found" }),
    });

    await expect(deleteDocument("missing")).rejects.toMatchObject({
      status: 404,
      message: "Document not found",
    });
  });
});

describe("listDocuments", () => {
  it("calls GET /documents", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve([]),
    });

    const result = await listDocuments();
    expect(result).toEqual([]);
    const [url] = mockFetch.mock.calls[0] as [string];
    expect(url).toContain("/documents");
  });
});
