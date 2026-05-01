import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import SpeciesCandidateModal from "../components/SpeciesCandidateModal";
import {
  clearSpecies,
  confirmSpecies,
  queryChatbot,
} from "../services/chatbotService";
import "../App.css";

function readOrCreateSessionId() {
  const key = "chatbot-session-id";
  const existed = localStorage.getItem(key);
  if (existed) {
    return existed;
  }
  const created = `session-${Date.now()}-${Math.random().toString(36).slice(2, 9)}`;
  localStorage.setItem(key, created);
  return created;
}

function loadImage(file) {
  return new Promise((resolve, reject) => {
    const img = new Image();
    const objectUrl = URL.createObjectURL(file);
    img.onload = () => {
      URL.revokeObjectURL(objectUrl);
      resolve(img);
    };
    img.onerror = (error) => {
      URL.revokeObjectURL(objectUrl);
      reject(error);
    };
    img.src = objectUrl;
  });
}

async function fileToCompressedDataUrl(file) {
  const image = await loadImage(file);
  const maxSize = 1280;
  const ratio = Math.min(1, maxSize / Math.max(image.width, image.height));
  const width = Math.max(1, Math.round(image.width * ratio));
  const height = Math.max(1, Math.round(image.height * ratio));

  const canvas = document.createElement("canvas");
  canvas.width = width;
  canvas.height = height;
  const context = canvas.getContext("2d", { alpha: false });
  context.drawImage(image, 0, 0, width, height);

  return canvas.toDataURL("image/jpeg", 0.82);
}

function ChatbotPage() {
  const [searchParams] = useSearchParams();
  const initialSpeciesId = searchParams.get("speciesId") || "";
  const initialSpeciesName = searchParams.get("speciesName") || "";
  const [sessionId] = useState(() => readOrCreateSessionId());
  const [question, setQuestion] = useState("");
  const [selectedFile, setSelectedFile] = useState(null);
  const [selectedFilePreview, setSelectedFilePreview] = useState("");
  const [activeSpeciesName, setActiveSpeciesName] = useState("");
  const [messages, setMessages] = useState(() =>
    initialSpeciesId
      ? []
      : [
          {
            role: "assistant",
            text: "Xin chào! Tôi là trợ lý nhận diện động vật. Bạn có thể dán ảnh bằng Ctrl+V, kéo thả ảnh vào ô chat hoặc bấm Chọn ảnh để gửi ảnh và đặt câu hỏi.",
          },
        ],
  );
  const [pendingCandidates, setPendingCandidates] = useState([]);
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [isSending, setIsSending] = useState(false);
  const [isPreparingImage, setIsPreparingImage] = useState(false);
  const [loadingText, setLoadingText] = useState("");
  const fileInputRef = useRef(null);
  const messagesEndRef = useRef(null);
  const didInitializeSpeciesRef = useRef(false);

  const canSend = useMemo(() => {
    return question.trim() || selectedFile;
  }, [question, selectedFile]);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({
      behavior: "smooth",
      block: "end",
    });
  }, [messages, isSending]);

  useEffect(() => {
    document.body.classList.add("chatbot-background");

    return () => {
      document.body.classList.remove("chatbot-background");
    };
  }, []);

  useEffect(() => {
    return () => {
      if (selectedFilePreview) {
        URL.revokeObjectURL(selectedFilePreview);
      }
    };
  }, [selectedFilePreview]);

  useEffect(() => {
    if (!initialSpeciesId || didInitializeSpeciesRef.current) {
      return;
    }

    didInitializeSpeciesRef.current = true;
    const activeName = initialSpeciesName || "loài này";

    setActiveSpeciesName(activeName);
    setMessages([
      {
        role: "assistant",
        text: `Loài đang được hỏi là ${activeName}.`,
      },
    ]);

    async function initializeActiveSpecies() {
      try {
        const response = await confirmSpecies({
          sessionId,
          speciesId: initialSpeciesId,
        });

        if (response?.activeSpeciesName) {
          setActiveSpeciesName(response.activeSpeciesName);
        }
      } catch {
        // Keep the optimistic intro message visible even if the API is down.
      }
    }

    initializeActiveSpecies();
  }, [initialSpeciesId, initialSpeciesName, sessionId]);

  function handlePickFile(event) {
    const file = event.target.files?.[0];
    if (!file) {
      return;
    }

    if (!file.type.startsWith("image/")) {
      return;
    }

    setSelectedImageFile(file);
  }

  function setSelectedImageFile(file) {
    if (selectedFilePreview) {
      URL.revokeObjectURL(selectedFilePreview);
    }

    const previewUrl = URL.createObjectURL(file);
    setSelectedFile(file);
    setSelectedFilePreview(previewUrl);
  }

  function clearPickedFile() {
    if (selectedFilePreview) {
      URL.revokeObjectURL(selectedFilePreview);
    }
    setSelectedFile(null);
    setSelectedFilePreview("");
    if (fileInputRef.current) {
      fileInputRef.current.value = "";
    }
  }

  function handlePaste(event) {
    const items = Array.from(event.clipboardData?.items || []);
    const imageItem = items.find((item) => item.type.startsWith("image/"));
    const file = imageItem?.getAsFile();

    if (!file) {
      return;
    }

    event.preventDefault();
    setSelectedImageFile(file);
  }

  function handleDragOver(event) {
    event.preventDefault();
  }

  function handleDrop(event) {
    event.preventDefault();
    const files = Array.from(event.dataTransfer?.files || []);
    const imageFile = files.find((file) => file.type.startsWith("image/"));

    if (imageFile) {
      setSelectedImageFile(imageFile);
    }
  }

  async function handleSubmit(event) {
    event.preventDefault();
    if (!canSend || isSending || isPreparingImage) {
      return;
    }

    const askedQuestion = question.trim();
    const currentFile = selectedFile;
    setLoadingText(
      currentFile
        ? "Đang xử lý và phân loại hình ảnh..."
        : "Đang xử lý câu hỏi...",
    );
    setIsSending(true);

    try {
      let imagePayload = null;
      if (currentFile) {
        setIsPreparingImage(true);
        imagePayload = await fileToCompressedDataUrl(currentFile);
      }

      setMessages((prev) => [
        ...prev,
        {
          role: "user",
          text: askedQuestion || "(Bạn vừa gửi ảnh để nhận diện)",
          imagePreview: imagePayload,
        },
      ]);
      setQuestion("");
      clearPickedFile();

      const response = await queryChatbot({
        sessionId,
        question: askedQuestion || null,
        imageUrl: imagePayload,
      });

      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          text: response?.answer || response?.message || "Đã nhận yêu cầu.",
        },
      ]);

      if (response?.activeSpeciesName) {
        setActiveSpeciesName(response.activeSpeciesName);
      } else if (response?.activeSpeciesId === null) {
        setActiveSpeciesName("");
      }

      const candidates = Array.isArray(response?.candidates)
        ? response.candidates
        : [];
      if (
        response?.status === "NEED_SPECIES_CONFIRM" &&
        candidates.length > 0
      ) {
        setPendingCandidates(candidates.slice(0, 6));
        setIsModalOpen(true);
      }
    } catch (error) {
      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          text: error?.response?.data?.message || "Không gọi được API chatbot.",
        },
      ]);
    } finally {
      setIsPreparingImage(false);
      setIsSending(false);
      setLoadingText("");
    }
  }

  async function handlePickSpecies(candidate) {
    if (!candidate?.speciesId) {
      return;
    }

    setLoadingText("Đang xác nhận loài đã chọn...");
    setIsSending(true);
    try {
      const response = await confirmSpecies({
        sessionId,
        speciesId: candidate.speciesId,
      });

      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          text: response?.answer || response?.message || "Đã xác nhận loài.",
        },
      ]);
      if (response?.activeSpeciesName) {
        setActiveSpeciesName(response.activeSpeciesName);
      }
      setIsModalOpen(false);
      setPendingCandidates([]);
    } catch (error) {
      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          text: error?.response?.data?.message || "Xác nhận loài thất bại.",
        },
      ]);
    } finally {
      setIsSending(false);
      setLoadingText("");
    }
  }

  async function handleClearSpecies() {
    try {
      const response = await clearSpecies({ sessionId });
      setActiveSpeciesName("");
      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          text: response?.message || "Đã xóa ngữ cảnh loài đang chọn.",
        },
      ]);
    } catch (error) {
      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          text: error?.response?.data?.message || "Xóa ngữ cảnh loài thất bại.",
        },
      ]);
    }
  }

  return (
    <main className="chat-shell">
      <header className="chat-page-banner">
        {/* <h2>
          <span>Hệ thống trợ lý động vật hoang dã</span>
          <span>Việt Nam</span>
        </h2> */}
        <div className="chat-page-banner-line" aria-hidden="true" />
      </header>

      <section className="chat-window" aria-label="Khung chat AI">
        <header className="chat-header">
          <div className="chat-header-main">
            <div className="chat-avatar">S</div>
            <div>
              <h1>Trợ lý WildlifeVN</h1>
              <p>Hỏi đáp về các loài động vật hoang dã tại Việt Nam</p>
            </div>
          </div>
          <div className="chat-header-actions">
            <Link className="chat-back-btn" to="/">
              ← Về thư viện
            </Link>
          </div>
        </header>

        {/* Removed persistent session banner per user request. */}

        <div className="chat-messages">
          {messages.length === 0 ? (
            <p className="chat-empty">
              Bắt đầu bằng cách gửi ảnh từ máy hoặc đặt câu hỏi.
            </p>
          ) : null}

          {messages.map((message, index) => {
            const isUser = message.role === "user";
            return (
              <article
                key={`${message.role}-${index}`}
                className={`chat-row ${isUser ? "user" : "assistant"}`}
              >
                {!isUser ? (
                  <div className="chat-message-avatar bot" aria-hidden="true">
                    ✿
                  </div>
                ) : null}

                <div className={`chat-bubble ${isUser ? "user" : "assistant"}`}>
                  {message.imagePreview ? (
                    <img
                      className="chat-bubble-image"
                      src={message.imagePreview}
                      alt="Ảnh đã gửi"
                    />
                  ) : null}
                  {isUser ? (
                    <p>{message.text}</p>
                  ) : (
                    <div className="chat-markdown">
                      <ReactMarkdown remarkPlugins={[remarkGfm]}>
                        {String(message.text || "")}
                      </ReactMarkdown>
                    </div>
                  )}
                </div>

                {isUser ? (
                  <div className="chat-message-avatar user" aria-hidden="true">
                    <svg
                      className="chat-message-avatar-icon"
                      viewBox="0 0 24 24"
                      aria-hidden="true"
                    >
                      <path
                        fill="currentColor"
                        d="M12 12a4.2 4.2 0 1 0 0-8.4 4.2 4.2 0 0 0 0 8.4Zm0 2.1c-4.04 0-7.35 2.43-7.35 5.4 0 .5.4.9.9.9h12.9a.9.9 0 0 0 .9-.9c0-2.97-3.31-5.4-7.35-5.4Z"
                      />
                    </svg>
                  </div>
                ) : null}
              </article>
            );
          })}

          {isSending ? (
            <article className="chat-row assistant">
              <div className="chat-message-avatar bot" aria-hidden="true">
                ✿
              </div>
              <div className="chat-bubble assistant chat-bubble-loading">
                <p className="chat-loading-line">
                  <span className="chat-spinner" aria-hidden="true" />
                  {loadingText || "AI đang xử lý..."}
                </p>
              </div>
            </article>
          ) : null}
          <div ref={messagesEndRef} />
        </div>

        <form
          onSubmit={handleSubmit}
          className="chat-composer"
          onPaste={handlePaste}
          onDragOver={handleDragOver}
          onDrop={handleDrop}
        >
          {selectedFilePreview ? (
            <div className="chat-picked-image">
              <img src={selectedFilePreview} alt="Ảnh vừa chọn" />
              <button type="button" onClick={clearPickedFile}>
                Bỏ ảnh
              </button>
            </div>
          ) : null}

          <div className="chat-input-row">
            <input
              onPaste={handlePaste}
              value={question}
              onChange={(event) => setQuestion(event.target.value)}
              placeholder="Nhập câu hỏi..."
            />

            <input
              ref={fileInputRef}
              type="file"
              accept="image/*"
              onChange={handlePickFile}
              hidden
            />

            <button
              type="button"
              className="chat-attach-btn"
              onClick={() => fileInputRef.current?.click()}
            >
              Chọn ảnh
            </button>

            <button
              type="submit"
              className="chat-send-btn"
              disabled={!canSend || isSending || isPreparingImage}
            >
              {isPreparingImage
                ? "Đang nén ảnh..."
                : isSending
                  ? "Đang gửi..."
                  : "Gửi"}
            </button>
          </div>

          <p className="chat-drop-hint">
            Bạn cũng có thể kéo thả ảnh vào vùng nhập hoặc dán ảnh từ clipboard.
          </p>
        </form>
      </section>

      <SpeciesCandidateModal
        open={isModalOpen}
        candidates={pendingCandidates}
        onClose={() => setIsModalOpen(false)}
        onSelect={handlePickSpecies}
      />
    </main>
  );
}

export default ChatbotPage;
