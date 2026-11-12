interface Props {
  onClick: () => void;
}

export default function SwapButton({ onClick }: Props) {
  return (
    <button
      onClick={onClick}
      className="flex h-10 w-10 items-center justify-center rounded-full border border-gray-300 bg-white text-gray-500 hover:bg-gray-50 hover:text-gray-700 focus:outline-none self-center cursor-pointer"
      aria-label="Swap origin and destination"
      data-testid="swap-button"
    >
      <svg className="h-5 w-5" viewBox="0 0 24 24" fill="currentColor">
        <path d="M6.99 11L3 15l3.99 4v-3H14v-2H6.99v-3zM21 9l-3.99-4v3H10v2h7.01v3L21 9z"/>
      </svg>
    </button>
  );
}
