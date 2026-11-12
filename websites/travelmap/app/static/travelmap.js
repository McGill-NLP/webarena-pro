(() => {
  function parseIso(isoDate) {
    return new Date(`${isoDate}T12:00:00`);
  }

  function toIso(dateValue) {
    return dateValue.toISOString().slice(0, 10);
  }

  function todayIso() {
    const now = new Date();
    const month = String(now.getMonth() + 1).padStart(2, "0");
    const day = String(now.getDate()).padStart(2, "0");
    return `${now.getFullYear()}-${month}-${day}`;
  }

  function addDays(isoDate, dayCount) {
    const dateValue = parseIso(isoDate);
    dateValue.setDate(dateValue.getDate() + dayCount);
    return toIso(dateValue);
  }

  function addMonths(dateValue, monthCount) {
    return new Date(dateValue.getFullYear(), dateValue.getMonth() + monthCount, 1);
  }

  function formatLabel(isoDate) {
    if (!isoDate) {
      return "Add date";
    }
    return parseIso(isoDate).toLocaleDateString(undefined, {
      month: "short",
      day: "numeric",
    });
  }

  function formatMonth(dateValue) {
    return dateValue.toLocaleDateString(undefined, {
      month: "long",
      year: "numeric",
    });
  }

  function differenceInNights(startIso, endIso) {
    return Math.round((parseIso(endIso) - parseIso(startIso)) / 86400000);
  }

  function rangeNightDates(startIso, endIso) {
    const totalNights = differenceInNights(startIso, endIso);
    return Array.from({ length: Math.max(totalNights, 0) }, (_, index) => addDays(startIso, index));
  }

  function initFilterDropdown(root) {
    const summary = root.querySelector("[data-filter-summary]");
    const checkboxes = [...root.querySelectorAll('input[type="checkbox"][name="amenity"]')];
    if (!summary || !checkboxes.length) {
      return;
    }

    const syncSummary = () => {
      const selected = checkboxes
        .filter((checkbox) => checkbox.checked)
        .map((checkbox) => checkbox.value.trim())
        .filter(Boolean);
      summary.textContent = selected.length ? selected.join(", ") : "Any amenities";
    };

    checkboxes.forEach((checkbox) => {
      checkbox.addEventListener("change", syncSummary);
    });

    syncSummary();
  }

  function initDatePicker(root) {
    const payloadNode =
      root.querySelector("[data-date-picker-payload]") ||
      document.getElementById("listing-availability-data");
    const checkInInput = root.querySelector('[data-date-input="check_in"]');
    const checkOutInput = root.querySelector('[data-date-input="check_out"]');
    const checkInLabel = root.querySelector("[data-check-in-label]");
    const checkOutLabel = root.querySelector("[data-check-out-label]");
    const staySummary = root.querySelector("[data-stay-summary]");
    const priceSummary = root.querySelector("[data-price-summary]");
    const calendarGrid = root.querySelector("[data-calendar-grid]");
    const previousButton = root.querySelector("[data-calendar-prev]");
    const nextButton = root.querySelector("[data-calendar-next]");
    const clearButton = root.querySelector("[data-date-picker-clear]");
    const calendarPopover = root.querySelector("[data-calendar-popover]");
    const calendarToggleButtons = [...root.querySelectorAll("[data-calendar-toggle]")];
    const calendarCloseButton = root.querySelector("[data-calendar-close]");
    const manualDateEntry = root.querySelector(".manual-date-entry");

    if (
      !payloadNode ||
      !checkInInput ||
      !checkOutInput ||
      !checkInLabel ||
      !checkOutLabel ||
      !staySummary ||
      !priceSummary ||
      !calendarGrid ||
      !previousButton ||
      !nextButton ||
      !calendarPopover ||
      !calendarToggleButtons.length
    ) {
      return;
    }

    const payload = JSON.parse(payloadNode.textContent);
    const availability = new Map((payload.days || []).map((day) => [day.date, day]));
    const cleaningFee = Number(root.dataset.cleaningFee || 0);
    const serviceFee = Number(root.dataset.serviceFee || 0);
    const boundaryDate = payload.checkoutBoundaryDate || "";
    const assumeOpenWindow = Boolean(payload.assumeOpenWindow);
    const availableDates = [...availability.keys()].sort();
    const firstWindowDate = availableDates[0] || payload.firstAvailableDate || "";
    const lastNightDate = availableDates[availableDates.length - 1] || (boundaryDate ? addDays(boundaryDate, -1) : "");
    const lastWindowDate = boundaryDate || lastNightDate;
    const firstSelectableDate = payload.allowHistoricalDates
      ? firstWindowDate
      : [firstWindowDate, todayIso()].sort().at(-1);
    const calendarAnchorIso = payload.initialMonthDate || payload.firstAvailableDate || firstWindowDate;

    if (!firstWindowDate || !lastWindowDate) {
      return;
    }

    const state = {
      checkIn: payload.selectedCheckIn || "",
      checkOut: payload.selectedCheckOut || "",
      hoverDate: "",
      monthOffset: 0,
    };

    function setCalendarOpen(isOpen) {
      calendarPopover.hidden = !isOpen;
      calendarToggleButtons.forEach((button) => {
        button.setAttribute("aria-expanded", String(isOpen));
      });
    }

    function openCalendar() {
      setCalendarOpen(true);
    }

    function closeCalendar() {
      setCalendarOpen(false);
    }

    function isVisibleDate(isoDate) {
      return isoDate >= firstWindowDate && isoDate <= lastWindowDate;
    }

    function isSelectableDate(isoDate) {
      return isoDate >= firstSelectableDate && isoDate <= lastWindowDate;
    }

    function isNightAvailable(isoDate) {
      if (isoDate < firstSelectableDate) {
        return false;
      }
      if (availability.has(isoDate)) {
        return Boolean(availability.get(isoDate)?.is_available);
      }
      return assumeOpenWindow && isoDate >= firstWindowDate && isoDate < lastWindowDate;
    }

    function canSelectStart(isoDate) {
      return isoDate < lastWindowDate && isNightAvailable(isoDate);
    }

    function isValidCheckout(startIso, endIso) {
      if (!startIso || !endIso || endIso <= startIso || !isSelectableDate(endIso)) {
        return false;
      }
      return rangeNightDates(startIso, endIso).every((nightIso) => isNightAvailable(nightIso));
    }

    function clearSelection() {
      state.checkIn = "";
      state.checkOut = "";
      state.hoverDate = "";
    }

    function selectDate(isoDate) {
      if (isoDate === state.checkIn) {
        clearSelection();
        syncSummary();
        renderCalendar();
        return;
      }

      if (isoDate === state.checkOut) {
        state.checkOut = "";
        state.hoverDate = "";
        syncSummary();
        renderCalendar();
        return;
      }

      if (!state.checkIn || state.checkOut) {
        if (!canSelectStart(isoDate)) {
          return;
        }
        state.checkIn = isoDate;
        state.checkOut = "";
        state.hoverDate = "";
        syncSummary();
        renderCalendar();
        return;
      }

      if (isoDate <= state.checkIn) {
        if (canSelectStart(isoDate)) {
          state.checkIn = isoDate;
          state.checkOut = "";
          state.hoverDate = "";
          syncSummary();
          renderCalendar();
        }
        return;
      }

      if (isValidCheckout(state.checkIn, isoDate)) {
        state.checkOut = isoDate;
        state.hoverDate = "";
        syncSummary();
        renderCalendar();
        closeCalendar();
        return;
      }

      if (canSelectStart(isoDate)) {
        state.checkIn = isoDate;
        state.checkOut = "";
        state.hoverDate = "";
        syncSummary();
        renderCalendar();
      }
    }

    if (!canSelectStart(state.checkIn)) {
      clearSelection();
    } else if (state.checkOut && !isValidCheckout(state.checkIn, state.checkOut)) {
      state.checkOut = "";
    }

    function syncSummary() {
      checkInInput.setCustomValidity("");
      checkOutInput.setCustomValidity("");
      checkInInput.value = state.checkIn;
      checkOutInput.value = state.checkOut;
      checkInLabel.textContent = formatLabel(state.checkIn);
      checkOutLabel.textContent = formatLabel(state.checkOut);

      if (clearButton) {
        clearButton.hidden = !state.checkIn && !state.checkOut;
      }

      if (isValidCheckout(state.checkIn, state.checkOut)) {
        const nights = differenceInNights(state.checkIn, state.checkOut);
        staySummary.textContent = payload.filledPrefix
          ? `${payload.filledPrefix} ${formatLabel(state.checkIn)} to ${formatLabel(state.checkOut)}`
          : `${nights} night${nights === 1 ? "" : "s"} · ${formatLabel(state.checkIn)} to ${formatLabel(state.checkOut)}`;

        if (payload.showPricing) {
          const nightlyDates = rangeNightDates(state.checkIn, state.checkOut);
          const nightlyTotal = nightlyDates.reduce(
            (sum, isoDate) =>
              sum + Number(
                availability.get(isoDate)?.nightly_price ?? payload.defaultNightlyPrice ?? 0,
              ),
            0,
          );
          const totalPrice = nightlyTotal + cleaningFee + serviceFee;
          priceSummary.textContent = `$${Math.round(totalPrice)} total`;
        } else {
          priceSummary.textContent = `${nights} night${nights === 1 ? "" : "s"} selected`;
        }
      } else {
        staySummary.textContent = payload.emptySummary || "Select check-in and check-out.";
        priceSummary.textContent = payload.emptyDetail || "";
      }
    }

    function renderCalendar() {
      const anchorDate = parseIso(calendarAnchorIso);
      const firstMonth = addMonths(new Date(anchorDate.getFullYear(), anchorDate.getMonth(), 1), state.monthOffset);
      const secondMonth = addMonths(firstMonth, 1);
      const previewEnd =
        !state.checkOut && state.hoverDate && isValidCheckout(state.checkIn, state.hoverDate)
          ? state.hoverDate
          : "";
      const activeRangeEnd = state.checkOut || previewEnd;
      const firstVisibleMonth = new Date(
        parseIso(firstWindowDate).getFullYear(),
        parseIso(firstWindowDate).getMonth(),
        1,
      );
      const lastVisibleMonth = new Date(
        parseIso(lastWindowDate).getFullYear(),
        parseIso(lastWindowDate).getMonth(),
        1,
      );

      previousButton.disabled = firstMonth.getTime() <= firstVisibleMonth.getTime();
      nextButton.disabled = secondMonth.getTime() >= lastVisibleMonth.getTime();

      calendarGrid.innerHTML = [firstMonth, secondMonth]
        .map((monthDate) => {
          const year = monthDate.getFullYear();
          const month = monthDate.getMonth();
          const monthStart = new Date(year, month, 1);
          const monthEnd = new Date(year, month + 1, 0);
          const leadingBlanks = monthStart.getDay();
          const cells = [];

          for (let index = 0; index < leadingBlanks; index += 1) {
            cells.push('<span class="calendar-spacer" aria-hidden="true"></span>');
          }

          for (let dayNumber = 1; dayNumber <= monthEnd.getDate(); dayNumber += 1) {
            const isoDate = toIso(new Date(year, month, dayNumber));
            const isBoundaryDate = isoDate === boundaryDate;
            const isInWindow = isVisibleDate(isoDate);
            const isPastDate = isoDate < firstSelectableDate;
            const canStart = !isBoundaryDate && canSelectStart(isoDate);
            const canCheckout = Boolean(state.checkIn) && isValidCheckout(state.checkIn, isoDate);
            const isBlocked = isInWindow && !canStart && !isBoundaryDate;
            const isSelectedStart = isoDate === state.checkIn;
            const isSelectedEnd = isoDate === activeRangeEnd;
            const isInRange = Boolean(
              state.checkIn && activeRangeEnd && isoDate >= state.checkIn && isoDate <= activeRangeEnd,
            );
            const isBeforePendingStart = Boolean(state.checkIn && !state.checkOut && isoDate < state.checkIn);
            const isRangeHead = Boolean(isInRange && isoDate > state.checkIn && Number(dayNumber) === 1);
            const isRangeTail = Boolean(isInRange && isoDate < activeRangeEnd && isoDate === toIso(monthEnd));
            const isPreview = !state.checkOut && state.hoverDate && activeRangeEnd === state.hoverDate && isInRange;
            const isDisabled = !isInWindow;
            const statusLabel = !canStart && canCheckout
              ? "Checkout only"
              : isBlocked
                ? "Unavailable"
                : isBoundaryDate
                  ? "Checkout only"
                  : canStart
                    ? "Available"
                    : "Not selectable";
            const classNames = [
              "calendar-day",
              canStart ? "is-available" : "",
              isBlocked ? "is-blocked" : "",
              isBoundaryDate ? "is-checkout-edge" : "",
              isSelectedStart ? "range-start" : "",
              isSelectedEnd ? "range-end" : "",
              isInRange ? "in-range" : "",
              isRangeHead ? "range-head" : "",
              isRangeTail ? "range-tail" : "",
              isPreview ? "is-preview" : "",
              isPastDate ? "is-past" : "",
              isBeforePendingStart ? "is-before-start" : "",
              canCheckout ? "can-checkout" : "",
            ]
              .filter(Boolean)
              .join(" ");

            cells.push(`
              <button
                type="button"
                class="${classNames}"
                data-date="${isoDate}"
                ${isDisabled || isPastDate || (!canStart && !canCheckout) ? "disabled" : ""}
                aria-pressed="${isSelectedStart || isSelectedEnd ? "true" : "false"}"
                aria-label="${isoDate}: ${statusLabel}"
                title="${statusLabel}"
              >
                <span>${dayNumber}</span>
              </button>
            `);
          }

          return `
            <section class="calendar-month">
              <div class="calendar-month-header">
                <strong>${formatMonth(monthDate)}</strong>
              </div>
              <div class="calendar-weekdays">
                <span>S</span>
                <span>M</span>
                <span>T</span>
                <span>W</span>
                <span>T</span>
                <span>F</span>
                <span>S</span>
              </div>
              <div class="calendar-days">${cells.join("")}</div>
            </section>
          `;
        })
        .join("");

      calendarGrid.querySelectorAll("[data-date]").forEach((button) => {
        const isoDate = button.dataset.date;

        button.addEventListener("pointerdown", (event) => {
          if (button.disabled) {
            return;
          }
          event.preventDefault();
          selectDate(isoDate);
        });

        button.addEventListener("keydown", (event) => {
          if (event.key !== "Enter" && event.key !== " ") {
            return;
          }
          event.preventDefault();
          selectDate(isoDate);
        });
      });
    }

    previousButton.addEventListener("click", () => {
      state.monthOffset -= 1;
      renderCalendar();
    });

    nextButton.addEventListener("click", () => {
      state.monthOffset += 1;
      renderCalendar();
    });

    calendarToggleButtons.forEach((button) => {
      button.addEventListener("click", () => {
        if (calendarPopover.hidden) {
          openCalendar();
        } else {
          closeCalendar();
        }
      });
    });

    if (calendarCloseButton) {
      calendarCloseButton.addEventListener("click", closeCalendar);
    }

    document.addEventListener("pointerdown", (event) => {
      if (
        calendarPopover.hidden ||
        calendarPopover.contains(event.target) ||
        calendarToggleButtons.some((button) => button.contains(event.target))
      ) {
        return;
      }
      closeCalendar();
    });

    document.addEventListener("keydown", (event) => {
      if (event.key === "Escape" && !calendarPopover.hidden) {
        closeCalendar();
        calendarToggleButtons[0].focus();
      }
    });

    if (clearButton) {
      clearButton.addEventListener("click", () => {
        clearSelection();
        state.monthOffset = 0;
        syncSummary();
        renderCalendar();
      });
    }

    function syncFromManualInputs() {
      const requestedCheckIn = checkInInput.value;
      const requestedCheckOut = checkOutInput.value;
      checkInInput.setCustomValidity("");
      checkOutInput.setCustomValidity("");

      if (!requestedCheckIn) {
        checkInInput.setCustomValidity("Choose a check-in date.");
        return false;
      }
      if (!requestedCheckOut) {
        checkOutInput.setCustomValidity("Choose a check-out date.");
        return false;
      }
      if (requestedCheckIn && !canSelectStart(requestedCheckIn)) {
        checkInInput.setCustomValidity("That check-in night is unavailable.");
        return false;
      }
      if (
        requestedCheckIn &&
        requestedCheckOut &&
        !isValidCheckout(requestedCheckIn, requestedCheckOut)
      ) {
        checkOutInput.setCustomValidity("That stay includes one or more unavailable nights.");
        return false;
      }

      state.checkIn = requestedCheckIn;
      state.checkOut = requestedCheckOut;
      state.hoverDate = "";
      syncSummary();
      renderCalendar();
      return true;
    }

    checkInInput.addEventListener("change", syncFromManualInputs);
    checkOutInput.addEventListener("change", syncFromManualInputs);
    root.addEventListener("submit", (event) => {
      if (!syncFromManualInputs()) {
        event.preventDefault();
        if (manualDateEntry) {
          manualDateEntry.open = true;
        }
        root.reportValidity();
      }
    });

    syncSummary();
    renderCalendar();
  }

  document.querySelectorAll("[data-filter-dropdown]").forEach(initFilterDropdown);
  document.querySelectorAll("[data-date-picker]").forEach(initDatePicker);
})();
