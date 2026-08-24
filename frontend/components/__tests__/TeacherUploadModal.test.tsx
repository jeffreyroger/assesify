import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { TeacherUploadModal } from "@/components/TeacherUploadModal";

vi.mock("@/lib/api", async () => {
    const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
    return { ...actual, default: { ...actual.default, uploadMaterial: vi.fn() } };
});

import api from "@/lib/api";

function makeFile(name = "notes.pdf") {
    return new File(["dummy content"], name, { type: "application/pdf" });
}

async function selectFile(file = makeFile()) {
    const input = document.querySelector('input[type="file"]') as HTMLInputElement;
    await userEvent.upload(input, file);
}

async function reachConfigStep() {
    await selectFile();
    await userEvent.click(screen.getByRole("button", { name: /continue/i }));
}

beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(api.uploadMaterial).mockResolvedValue({ quiz_id: 1 } as never);
});

afterEach(() => vi.restoreAllMocks());

describe("TeacherUploadModal", () => {
    it("renders nothing when closed", () => {
        const { container } = render(<TeacherUploadModal isOpen={false} onClose={vi.fn()} />);
        expect(container).toBeEmptyDOMElement();
    });

    it("starts on the upload step with Continue disabled", () => {
        render(<TeacherUploadModal isOpen onClose={vi.fn()} />);
        expect(screen.getByText("Upload Materials")).toBeInTheDocument();
        expect(screen.getByText(/Click or Drag to Upload/i)).toBeInTheDocument();
        expect(screen.getByRole("button", { name: /continue/i })).toBeDisabled();
    });

    it("shows the chosen file and enables Continue", async () => {
        render(<TeacherUploadModal isOpen onClose={vi.fn()} />);
        await selectFile(makeFile("policy-notes.pdf"));
        expect(await screen.findByText("policy-notes.pdf")).toBeInTheDocument();
        expect(screen.getByRole("button", { name: /continue/i })).toBeEnabled();
    });

    it("clears the chosen file via Remove", async () => {
        render(<TeacherUploadModal isOpen onClose={vi.fn()} />);
        await selectFile();
        await userEvent.click(await screen.findByRole("button", { name: /remove/i }));
        expect(screen.getByText(/Click or Drag to Upload/i)).toBeInTheDocument();
        expect(screen.getByRole("button", { name: /continue/i })).toBeDisabled();
    });

    it("accepts a dropped file", async () => {
        render(<TeacherUploadModal isOpen onClose={vi.fn()} />);
        const dropzone = screen.getByText(/Click or Drag to Upload/i).closest("div")!.parentElement!;
        fireEvent.dragEnter(dropzone);
        fireEvent.drop(dropzone, { dataTransfer: { files: [makeFile("dropped.pdf")] } });
        expect(await screen.findByText("dropped.pdf")).toBeInTheDocument();
    });

    it("requires a title and subject before generating", async () => {
        render(<TeacherUploadModal isOpen onClose={vi.fn()} />);
        await reachConfigStep();
        const generate = screen.getByRole("button", { name: /generate quiz/i });
        expect(generate).toBeDisabled();
        await userEvent.type(screen.getByPlaceholderText(/Week 5 Assessment/i), "Week 5");
        expect(generate).toBeDisabled();
        await userEvent.type(screen.getByPlaceholderText(/e.g. Biology/i), "Budgeting");
        expect(generate).toBeEnabled();
    });

    it("navigates back to the upload step", async () => {
        render(<TeacherUploadModal isOpen onClose={vi.fn()} />);
        await reachConfigStep();
        await userEvent.click(screen.getByRole("button", { name: /back/i }));
        // Back returns to the upload step with the chosen file still selected.
        expect(screen.getByText("notes.pdf")).toBeInTheDocument();
        expect(screen.getByRole("button", { name: /continue/i })).toBeEnabled();
    });

    it("submits the configured generation request and shows success", async () => {
        const onClose = vi.fn();
        render(<TeacherUploadModal isOpen onClose={onClose} />);
        await reachConfigStep();
        await userEvent.type(screen.getByPlaceholderText(/Week 5 Assessment/i), "Week 5");
        await userEvent.type(screen.getByPlaceholderText(/e.g. Biology/i), "Budgeting");
        await userEvent.selectOptions(screen.getAllByRole("combobox")[0], "hard");
        await userEvent.selectOptions(screen.getAllByRole("combobox")[1], "20");
        await userEvent.click(screen.getByRole("button", { name: /generate quiz/i }));

        await waitFor(() => expect(api.uploadMaterial).toHaveBeenCalledTimes(1));
        const form = vi.mocked(api.uploadMaterial).mock.calls[0][0] as FormData;
        expect(form.get("title")).toBe("Week 5");
        expect(form.get("subject")).toBe("Budgeting");
        expect(form.get("difficulty")).toBe("hard");
        expect(form.get("numQuestions")).toBe("20");
        expect(form.get("file")).toBeInstanceOf(File);

        expect(await screen.findByText("Quiz Generated!")).toBeInTheDocument();
        await userEvent.click(screen.getByRole("button", { name: /done/i }));
        expect(onClose).toHaveBeenCalledTimes(1);
    });

    it("returns to the config step and alerts when generation fails", async () => {
        vi.mocked(api.uploadMaterial).mockRejectedValue(new Error("Gemini down"));
        const alertSpy = vi.spyOn(window, "alert").mockImplementation(() => {});
        vi.spyOn(console, "error").mockImplementation(() => {});
        render(<TeacherUploadModal isOpen onClose={vi.fn()} />);

        await reachConfigStep();
        await userEvent.type(screen.getByPlaceholderText(/Week 5 Assessment/i), "T");
        await userEvent.type(screen.getByPlaceholderText(/e.g. Biology/i), "S");
        await userEvent.click(screen.getByRole("button", { name: /generate quiz/i }));

        await waitFor(() => expect(alertSpy).toHaveBeenCalled());
        expect(screen.getByRole("button", { name: /generate quiz/i })).toBeInTheDocument();
    });

    it("closes via the header X button", async () => {
        const onClose = vi.fn();
        const { container } = render(<TeacherUploadModal isOpen onClose={onClose} />);
        const closeButton = container.querySelector("button")!;
        await userEvent.click(closeButton);
        expect(onClose).toHaveBeenCalledTimes(1);
    });
});
