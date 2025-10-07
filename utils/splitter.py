class TextSplitter:
    def __init__(
        self, chunk_size: int = 1000, overlap: int = 100, separator: str = " "
    ):
        print(
            f"Initializing TextSplitter with chunk_size={chunk_size}, overlap={overlap}, separator={separator}"
        )
        self.chunk_size = chunk_size
        self.overlap = overlap
        self.separator = separator

    def split(self, text: str) -> list[str]:
        print(
            f"Splitting text into chunks of size {self.chunk_size} with overlap {self.overlap}"
        )
        words = text.split()
        chunks = []
        for i in range(0, len(words), self.chunk_size):
            chunks.append(self.separator.join(words[i : i + self.chunk_size]))
        print(f"Split into {len(chunks)} chunks")
        return chunks
