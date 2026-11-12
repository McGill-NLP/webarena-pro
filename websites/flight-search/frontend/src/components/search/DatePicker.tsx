interface Props {
  label: string;
  value: string; // YYYY-MM-DD
  onChange: (v: string) => void;
  min?: string; // YYYY-MM-DD
  max?: string; // YYYY-MM-DD
  testId?: string;
}

export default function DatePicker({ label, value, onChange, min, max, testId }: Props) {
  const emptyClass = value ? '' : ' date-input-empty';

  return (
    <div className="relative min-w-[150px]" data-testid={testId}>
      <label className="absolute -top-2 left-3 bg-white px-1 text-xs text-gray-500 z-10">{label}</label>
      <input
        type="date"
        value={value}
        min={min}
        max={max}
        onChange={e => onChange(e.target.value)}
        placeholder="mm/dd/yyyy"
        className={`w-full rounded-md border border-gray-300 px-3 py-3 text-sm text-gray-900 hover:border-gray-400 focus:border-[#1a73e8] focus:outline-none cursor-pointer${emptyClass}`}
        aria-label={label}
        data-testid={testId ? `${testId}-input` : undefined}
      />
      {!value && (
        <span className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-sm text-gray-400">
          mm/dd/yyyy
        </span>
      )}
    </div>
  );
}
