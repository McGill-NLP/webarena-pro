export default function Loading() {
  return (
    <div className="flex flex-col items-center justify-center py-20" data-testid="loading">
      <div className="h-10 w-10 animate-spin rounded-full border-4 border-gray-200 border-t-[#1a73e8]" />
      <p className="mt-4 text-sm text-gray-500">Searching flights...</p>
    </div>
  );
}
