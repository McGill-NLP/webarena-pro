interface Props {
  hasFilters: boolean;
  onClearFilters?: () => void;
}

export default function NoResults({ hasFilters, onClearFilters }: Props) {
  return (
    <div className="flex flex-col items-center justify-center py-16 text-center" data-testid="no-results">
      <svg className="mb-4 h-16 w-16 text-gray-300" viewBox="0 0 24 24" fill="currentColor">
        <path d="M21 16v-2l-8-5V3.5c0-.83-.67-1.5-1.5-1.5S10 2.67 10 3.5V9l-8 5v2l8-2.5V19l-2 1.5V22l3.5-1 3.5 1v-1.5L13 19v-5.5l8 2.5z"/>
      </svg>
      <h3 className="text-lg font-medium text-gray-700">No flights found</h3>
      <p className="mt-1 text-sm text-gray-500">
        {hasFilters
          ? 'Try adjusting your filters or search criteria.'
          : 'No direct or connecting flights available for this route.'}
      </p>
      {hasFilters && onClearFilters && (
        <button
          onClick={onClearFilters}
          className="mt-4 text-sm font-medium text-[#1a73e8] hover:underline cursor-pointer"
          data-testid="clear-filters-button"
        >
          Clear all filters
        </button>
      )}
    </div>
  );
}
