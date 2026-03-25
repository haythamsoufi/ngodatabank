// Handles the Document Upload modal open/close and file selection wiring
// Relies on data attributes on the modal element for localized strings.
//
// SECURITY WARNING: All file validations performed here are CLIENT-SIDE ONLY
// and can be bypassed by malicious users. Server-side validation is MANDATORY
// for all file uploads including:
// - File type validation (MIME type and magic bytes)
// - File size limits
// - Virus scanning
// - Authorization checks for document operations
// - Path traversal prevention

export function initDocumentUpload() {
  const modal = document.getElementById('document-upload-modal');
  if (!modal) return;

  const modalTitle = document.getElementById('modal-title');
  const fieldNameDisplay = document.getElementById('document-field-name');
  const modalFileInput = document.getElementById('modal-document-file');
  const confirmUploadBtn = document.getElementById('confirm-upload-btn');

  const t = {
    uploadLabel: modal.dataset.labelUpload || 'Upload Document',
    replaceLabel: modal.dataset.labelReplace || 'Replace Document',
    editLabel: modal.dataset.labelEdit || 'Edit Document',
    errorSize: modal.dataset.errorSize || 'File size exceeds 25MB limit. Please select a smaller file.',
    errorType: modal.dataset.errorType || 'Invalid file type. Please select a PDF, Word, Excel, PowerPoint, or Text file.',
    documentUpdated: modal.dataset.documentUpdated || 'Document Updated',
    documentSelected: modal.dataset.documentSelected || 'Document Selected',
    maxDocumentsAllowed: modal.dataset.maxDocumentsAllowed || 'Maximum documents allowed',
    errorCancelDeletion: modal.dataset.errorCancelDeletion || 'Cannot cancel deletion. This field allows a maximum of %(max)s document(s). Remove the newly added document first.',
    errorPeriodRequired: modal.dataset.errorPeriodRequired || 'Please select a Year/Period for the document.',
    documentPendingSave: modal.dataset.documentPendingSave || 'Please save the form first before editing this document.',
    invalidDocumentId: modal.dataset.invalidDocumentId || 'Unable to edit: document ID is invalid. Please refresh the page and try again.',
  };

  let currentFieldId = null;
  let currentFieldLabel = null;
  let currentIsRequired = false;
  let currentHasExisting = false;
  let currentDocumentId = null;
  let isEditMode = false;

  // Track queued documents for each field (fieldId => array of {file, language, hiddenInputName})
  const queuedDocuments = {};

  // Track documents marked for deletion (docId => {element, fieldId, hiddenInput})
  const documentsMarkedForDeletion = {};

  // Month names for period generation
  const monthNames = {
    '01': 'Jan', '02': 'Feb', '03': 'Mar', '04': 'Apr',
    '05': 'May', '06': 'Jun', '07': 'Jul', '08': 'Aug',
    '09': 'Sep', '10': 'Oct', '11': 'Nov', '12': 'Dec'
  };

  // Populate year <select> elements (scrollable list) and default to current year when empty.
  function ensureYearSelectOptionsAndDefaults() {
    const currentYear = new Date().getFullYear();

    const yearSelectIds = [
      'modal-single-year',
      'modal-start-year',
      'modal-end-year',
      'modal-start-month-year',
      'modal-end-month-year'
    ];

    yearSelectIds.forEach((id) => {
      const el = document.getElementById(id);
      if (!el || el.tagName !== 'SELECT') return;

      // If it already contains numeric year options, don't repopulate.
      const hasYearOptions = Array.from(el.options || []).some(o => /^\d{4}$/.test(String(o.value || '')));
      if (!hasYearOptions) {
        const minYearAttr = parseInt(el.getAttribute('data-year-min') || el.getAttribute('min') || '2000', 10);
        const maxYearAttr = parseInt(el.getAttribute('data-year-max') || el.getAttribute('max') || '2100', 10);
        const minYear = Number.isFinite(minYearAttr) ? minYearAttr : 2000;
        const hardMax = Number.isFinite(maxYearAttr) ? maxYearAttr : 2100;
        const maxYear = Math.min(hardMax, currentYear + 5);

        // Preserve first option if it's an empty placeholder
        const placeholderOption = (el.options && el.options.length > 0 && !el.options[0].value)
          ? el.options[0].cloneNode(true)
          : null;

        el.innerHTML = '';
        if (placeholderOption) el.appendChild(placeholderOption);

        for (let y = maxYear; y >= minYear; y -= 1) {
          const opt = document.createElement('option');
          opt.value = String(y);
          opt.textContent = String(y);
          el.appendChild(opt);
        }
      }

      // Default to current year if empty (don’t override edit-mode populated values)
      if (!String(el.value || '').trim()) {
        el.value = String(currentYear);
      }
    });
  }

  // --- Helper functions to centralize button/icon state ---
  function setIcon(uploadBtn, kind /* 'upload' | 'plus' */) {
    if (!uploadBtn) return;
    const icon = uploadBtn.querySelector('i');
    if (!icon) return;
    if (kind === 'plus') {
      icon.classList.remove('fa-upload');
      icon.classList.add('fa-plus');
    } else {
      icon.classList.remove('fa-plus');
      icon.classList.add('fa-upload');
    }
  }

  function setEmptyState(uploadBtn) {
    if (!uploadBtn) return;
    uploadBtn.dataset.hasExisting = 'false';
    setIcon(uploadBtn, 'upload');
    uploadBtn.classList.add('text-gray-400', 'hover:text-purple-600', 'border-2', 'border-dashed',
                            'border-gray-300', 'hover:border-purple-400', 'rounded-lg', 'py-2', 'px-4');
    uploadBtn.classList.remove('text-purple-600', 'hover:text-purple-700');
    if (uploadBtn.parentElement) uploadBtn.parentElement.style.display = '';
  }

  function setHasDocsState(uploadBtn) {
    if (!uploadBtn) return;
    uploadBtn.dataset.hasExisting = 'true';
    setIcon(uploadBtn, 'plus');
    uploadBtn.classList.remove('text-gray-400', 'hover:text-purple-600', 'border-2', 'border-dashed',
                               'border-gray-300', 'hover:border-purple-400', 'rounded-lg', 'py-2', 'px-4');
    uploadBtn.classList.add('text-purple-600', 'hover:text-purple-700');
  }

  function updateUploadButtonVisibility(fieldContainer, fieldId) {
    if (!fieldContainer) return;
    const uploadBtn = fieldContainer.querySelector('.document-upload-btn');
    if (!uploadBtn) return;
    const maxDocuments = getMaxDocumentsForField(fieldId);
    const currentCount = getCurrentDocumentCount(fieldId);
    if (maxDocuments && currentCount >= maxDocuments) {
      if (uploadBtn.parentElement) uploadBtn.parentElement.style.display = 'none';
    } else {
      if (uploadBtn.parentElement) uploadBtn.parentElement.style.display = '';
    }
  }

  // Configure modal field visibility based on field configuration
  function configureModalFields(config) {
    const languageSection = document.getElementById('modal-document-language')?.closest('div');
    const typeSection = document.getElementById('modal-document-type-section');
    const yearSection = document.getElementById('modal-year-section');
    const publicSection = document.getElementById('modal-public-section');

    // Show/hide sections based on config
    if (languageSection) {
      languageSection.classList.toggle('hidden', config.show_language === false);
    }
    if (typeSection) {
      typeSection.classList.toggle('hidden', !config.show_document_type);
    }
    if (yearSection) {
      yearSection.classList.toggle('hidden', !config.show_year);
      // Initialize period handlers and filter types if shown
      if (config.show_year) {
        initializePeriodHandlers();
        filterPeriodTypes(config);
        ensureYearSelectOptionsAndDefaults();
        generatePeriodName();
      }
    }
    if (publicSection) {
      publicSection.classList.toggle('hidden', !config.show_public_checkbox);
    }

    // Adjust grid layout based on visible fields
    adjustModalLayout(config);

    // Reset fields
    resetConfigurableFields(config);
  }

  // Adjust modal layout based on which fields are visible
  function adjustModalLayout(config) {
    const gridContainer = modal.querySelector('.grid.grid-cols-1.md\\:grid-cols-2');
    if (!gridContainer) return;

    // Check if right column has any visible fields
    const hasRightColumnFields = config.show_year || config.show_public_checkbox;

    if (!hasRightColumnFields) {
      // Switch to single column layout
      gridContainer.classList.remove('md:grid-cols-2');
      gridContainer.classList.add('md:grid-cols-1');
    } else {
      // Use two column layout
      gridContainer.classList.remove('md:grid-cols-1');
      gridContainer.classList.add('md:grid-cols-2');
    }
  }

  // Filter period types based on allowed options
  function filterPeriodTypes(config) {
    const periodTypeSelect = document.getElementById('modal-period-type');
    if (!periodTypeSelect) return;

    // Get allowed period types
    const allowedTypes = [];
    if (config.allow_single_year !== false) allowedTypes.push('single-year');
    if (config.allow_year_range !== false) allowedTypes.push('year-range');
    if (config.allow_month_range !== false) allowedTypes.push('month-range');

    // If no types are allowed, allow all by default
    if (allowedTypes.length === 0) {
      allowedTypes.push('single-year', 'year-range', 'month-range');
    }

    // Show/hide options based on allowed types
    Array.from(periodTypeSelect.options).forEach(option => {
      if (allowedTypes.includes(option.value)) {
        option.style.display = '';
      } else {
        option.style.display = 'none';
      }
    });

    // Set default to first allowed type
    if (!allowedTypes.includes(periodTypeSelect.value)) {
      periodTypeSelect.value = allowedTypes[0];
      togglePeriodFields();
    }
  }

  // Reset configurable fields to default state
  function resetConfigurableFields(config) {
    const documentTypeSelect = document.getElementById('modal-document-type');
    const periodTypeSelect = document.getElementById('modal-period-type');
    const isPublicCheckbox = document.getElementById('modal-is-public');
    const languageSelect = document.getElementById('modal-document-language');

    if (documentTypeSelect) documentTypeSelect.value = '';
    if (languageSelect && !isEditMode) languageSelect.value = ''; // Don't reset in edit mode
    if (isPublicCheckbox) isPublicCheckbox.checked = false;

    // Reset file input (not applicable in edit mode as it's already reset)
    if (modalFileInput && !isEditMode) {
      modalFileInput.value = '';
    }

    // Set period type to first allowed type
    if (periodTypeSelect && config) {
      const allowedTypes = [];
      if (config.allow_single_year !== false) allowedTypes.push('single-year');
      if (config.allow_year_range !== false) allowedTypes.push('year-range');
      if (config.allow_month_range !== false) allowedTypes.push('month-range');

      if (allowedTypes.length === 0) {
        allowedTypes.push('single-year'); // Default fallback
      }

      // Only reset to default if not in edit mode
      if (!isEditMode) {
        periodTypeSelect.value = allowedTypes[0];
        togglePeriodFields();
      }
    } else if (periodTypeSelect && !isEditMode) {
      periodTypeSelect.value = 'single-year';
      togglePeriodFields();
    }

    // Clear all period fields (only in upload mode)
    if (!isEditMode) {
      const periodFields = [
        'modal-single-year', 'modal-start-year', 'modal-end-year',
        'modal-start-month-year', 'modal-start-month',
        'modal-end-month-year', 'modal-end-month', 'modal-year-value'
      ];
      periodFields.forEach(id => {
        const field = document.getElementById(id);
        if (field) field.value = '';
      });
      // Re-apply default year after clearing
      ensureYearSelectOptionsAndDefaults();
      generatePeriodName();
    }
  }

  // Initialize period field handlers
  function initializePeriodHandlers() {
    const periodTypeSelect = document.getElementById('modal-period-type');
    const singleYearField = document.getElementById('modal-single-year');
    const startYearField = document.getElementById('modal-start-year');
    const endYearField = document.getElementById('modal-end-year');
    const startMonthYearField = document.getElementById('modal-start-month-year');
    const startMonthSelect = document.getElementById('modal-start-month');
    const endMonthYearField = document.getElementById('modal-end-month-year');
    const endMonthSelect = document.getElementById('modal-end-month');

    // Remove existing listeners
    if (periodTypeSelect && !periodTypeSelect.dataset.listenersAttached) {
      periodTypeSelect.addEventListener('change', togglePeriodFields);
      periodTypeSelect.dataset.listenersAttached = 'true';
    }

    // Attach input listeners for period generation and validation
    const periodInputs = [
      singleYearField, startYearField, endYearField,
      startMonthYearField, startMonthSelect,
      endMonthYearField, endMonthSelect
    ];

    periodInputs.forEach(input => {
      if (input && !input.dataset.listenersAttached) {
        const eventType = input.tagName === 'SELECT' ? 'change' : 'input';
        input.addEventListener(eventType, () => {
          validateDateRanges();
          generatePeriodName();
          validateUploadForm();
        });
        input.dataset.listenersAttached = 'true';
      }
    });
  }

  // Toggle period fields visibility
  function togglePeriodFields() {
    const periodType = document.getElementById('modal-period-type')?.value;

    // Clear validation errors when switching period types
    clearDateValidationErrors();

    // Hide all period fields
    document.querySelectorAll('.period-fields').forEach(field => {
      field.classList.add('hidden');
    });

    // Show relevant fields
    if (periodType === 'single-year') {
      document.getElementById('modal-single-year-fields')?.classList.remove('hidden');
    } else if (periodType === 'year-range') {
      document.getElementById('modal-year-range-fields')?.classList.remove('hidden');
    } else if (periodType === 'month-range') {
      document.getElementById('modal-month-range-fields')?.classList.remove('hidden');
    }

    generatePeriodName();
    validateUploadForm();
  }

  // Validate date ranges
  function validateDateRanges() {
    const periodType = document.getElementById('modal-period-type')?.value;
    let isValid = true;
    let errorMessage = '';

    // Clear previous errors
    clearDateValidationErrors();

    if (periodType === 'year-range') {
      const startYear = parseInt(document.getElementById('modal-start-year')?.value);
      const endYear = parseInt(document.getElementById('modal-end-year')?.value);

      if (startYear && endYear && startYear > endYear) {
        isValid = false;
        errorMessage = 'Start year cannot be later than end year.';
        markDateFieldInvalid('modal-start-year');
        markDateFieldInvalid('modal-end-year');
        showCombinedDateValidationError('modal-year-range-fields', errorMessage);
      }
    } else if (periodType === 'month-range') {
      const startYear = parseInt(document.getElementById('modal-start-month-year')?.value);
      const startMonth = parseInt(document.getElementById('modal-start-month')?.value);
      const endYear = parseInt(document.getElementById('modal-end-month-year')?.value);
      const endMonth = parseInt(document.getElementById('modal-end-month')?.value);

      if (startYear && startMonth && endYear && endMonth) {
        // Create date objects for comparison
        const startDate = new Date(startYear, startMonth - 1, 1);
        const endDate = new Date(endYear, endMonth - 1, 1);

        if (startDate > endDate) {
          isValid = false;
          errorMessage = 'Start period cannot be later than end period.';
          showDateValidationError('modal-start-month-year', errorMessage);
          showDateValidationError('modal-start-month', errorMessage);
          showDateValidationError('modal-end-month-year', errorMessage);
          showDateValidationError('modal-end-month', errorMessage);
        }
      }
    }

    return isValid;
  }

  // Show date validation error
  function showDateValidationError(fieldId, message) {
    const field = document.getElementById(fieldId);
    if (!field) return;

    // Add error styling
    field.classList.add('border-red-500', 'ring-2', 'ring-red-200');

    // Find or create error message element
    let errorDiv = field.parentElement.querySelector('.date-validation-error');
    if (!errorDiv) {
      errorDiv = document.createElement('div');
      errorDiv.className = 'date-validation-error text-red-600 text-xs mt-1';
      field.parentElement.appendChild(errorDiv);
    }
    errorDiv.textContent = message;
  }

  // Highlight a field as invalid without adding duplicate error text
  function markDateFieldInvalid(fieldId) {
    const field = document.getElementById(fieldId);
    if (!field) return;
    field.classList.add('border-red-500', 'ring-2', 'ring-red-200');
  }

  // Show a single validation message under a whole section (spans both fields)
  function showCombinedDateValidationError(sectionId, message) {
    const section = document.getElementById(sectionId);
    if (!section) return;

    let errorDiv = section.querySelector('.date-validation-error.date-validation-error-combined');
    if (!errorDiv) {
      errorDiv = document.createElement('div');
      errorDiv.className = 'date-validation-error date-validation-error-combined text-red-600 text-xs mt-1';
      section.appendChild(errorDiv);
    }
    errorDiv.textContent = message;
  }

  // Clear date validation errors
  function clearDateValidationErrors() {
    // Remove error styling from all period fields
    const periodFields = [
      'modal-single-year',
      'modal-start-year', 'modal-end-year',
      'modal-start-month-year', 'modal-start-month',
      'modal-end-month-year', 'modal-end-month'
    ];

    periodFields.forEach(fieldId => {
      const field = document.getElementById(fieldId);
      if (field) {
        field.classList.remove('border-red-500', 'ring-2', 'ring-red-200');
      }
    });

    // Remove error messages
    document.querySelectorAll('.date-validation-error').forEach(el => el.remove());
  }

  function isPeriodSectionVisible() {
    const yearSection = document.getElementById('modal-year-section');
    return !!(yearSection && !yearSection.classList.contains('hidden'));
  }

  // If the Year/Period selector is enabled for this field, enforce that a period is selected.
  // When showMessage=true, we highlight the relevant input and show a warning.
  function ensurePeriodSelected(showMessage = false) {
    if (!isPeriodSectionVisible()) return true;

    // Keep derived hidden field up to date
    generatePeriodName();

    const yearValue = document.getElementById('modal-year-value')?.value || '';
    if (yearValue) return true;

    if (showMessage) {
      const msg = t.errorPeriodRequired;
      const periodType = document.getElementById('modal-period-type')?.value;

      if (periodType === 'single-year') {
        showDateValidationError('modal-single-year', msg);
        document.getElementById('modal-single-year')?.focus();
      } else if (periodType === 'year-range') {
        showDateValidationError('modal-start-year', msg);
        document.getElementById('modal-start-year')?.focus();
      } else if (periodType === 'month-range') {
        showDateValidationError('modal-start-month-year', msg);
        document.getElementById('modal-start-month-year')?.focus();
      } else {
        showDateValidationError('modal-single-year', msg);
        document.getElementById('modal-single-year')?.focus();
      }

      if (window.showAlert) {
        window.showAlert(msg, 'warning');
      } else {
        // Avoid native alert/confirm; custom dialogs should be loaded globally.
        console.warn(msg);
      }
    }

    return false;
  }

  // Generate period name based on current values
  function generatePeriodName() {
    // Validate dates before generating period name
    if (!validateDateRanges()) {
      // Don't generate period name if validation fails
      return;
    }

    const periodType = document.getElementById('modal-period-type')?.value;
    let periodName = '';

    if (periodType === 'single-year') {
      const year = document.getElementById('modal-single-year')?.value;
      if (year) periodName = year;
    } else if (periodType === 'year-range') {
      const startYear = document.getElementById('modal-start-year')?.value;
      const endYear = document.getElementById('modal-end-year')?.value;
      if (startYear && endYear) {
        periodName = startYear === endYear ? startYear : `${startYear}-${endYear}`;
      } else if (startYear) {
        periodName = startYear;
      }
    } else if (periodType === 'month-range') {
      const startYear = document.getElementById('modal-start-month-year')?.value;
      const startMonth = document.getElementById('modal-start-month')?.value;
      const endYear = document.getElementById('modal-end-month-year')?.value;
      const endMonth = document.getElementById('modal-end-month')?.value;

      if (startYear && startMonth && endYear && endMonth) {
        const startMonthName = monthNames[startMonth];
        const endMonthName = monthNames[endMonth];

        if (startYear === endYear && startMonth === endMonth) {
          periodName = `${startMonthName} ${startYear}`;
        } else if (startYear === endYear) {
          periodName = `${startMonthName}-${endMonthName} ${startYear}`;
        } else {
          periodName = `${startMonthName} ${startYear}-${endMonthName} ${endYear}`;
        }
      }
    }

    // Update hidden field
    const hiddenYearField = document.getElementById('modal-year-value');
    if (hiddenYearField) {
      hiddenYearField.value = periodName || '';
    }
  }

  // Parse existing period and populate fields (for edit mode)
  function parseAndPopulatePeriod(periodStr) {
    if (!periodStr || periodStr === 'None' || periodStr === '' || periodStr === 'null') return;

    // Ensure the year selects are populated before setting .value
    ensureYearSelectOptionsAndDefaults();

    const periodTypeSelect = document.getElementById('modal-period-type');
    if (!periodTypeSelect) return;

    // Pattern matching
    const yearPattern = /^(\d{4})$/;
    const yearRangePattern = /^(\d{4})-(\d{4})$/;
    const monthPattern = /^([A-Za-z]{3})\s+(\d{4})$/;
    const monthRangePattern = /^([A-Za-z]{3})\s+(\d{4})-([A-Za-z]{3})\s+(\d{4})$/;
    const monthYearRangePattern = /^([A-Za-z]{3})-([A-Za-z]{3})\s+(\d{4})$/;

    const monthToNumber = {
      'Jan': '01', 'Feb': '02', 'Mar': '03', 'Apr': '04',
      'May': '05', 'Jun': '06', 'Jul': '07', 'Aug': '08',
      'Sep': '09', 'Oct': '10', 'Nov': '11', 'Dec': '12'
    };

    if (yearPattern.test(periodStr)) {
      // Single year: "2024"
      const match = periodStr.match(yearPattern);
      periodTypeSelect.value = 'single-year';
      const singleYearField = document.getElementById('modal-single-year');
      if (singleYearField) singleYearField.value = match[1];
    } else if (yearRangePattern.test(periodStr)) {
      // Year range: "2024-2025"
      const match = periodStr.match(yearRangePattern);
      periodTypeSelect.value = 'year-range';
      const startYearField = document.getElementById('modal-start-year');
      const endYearField = document.getElementById('modal-end-year');
      if (startYearField) startYearField.value = match[1];
      if (endYearField) endYearField.value = match[2];
    } else if (monthRangePattern.test(periodStr)) {
      // Month range: "Jan 2024-Dec 2025"
      const match = periodStr.match(monthRangePattern);
      periodTypeSelect.value = 'month-range';
      const startMonthSelect = document.getElementById('modal-start-month');
      const startMonthYearField = document.getElementById('modal-start-month-year');
      const endMonthSelect = document.getElementById('modal-end-month');
      const endMonthYearField = document.getElementById('modal-end-month-year');

      if (startMonthSelect) startMonthSelect.value = monthToNumber[match[1]];
      if (startMonthYearField) startMonthYearField.value = match[2];
      if (endMonthSelect) endMonthSelect.value = monthToNumber[match[3]];
      if (endMonthYearField) endMonthYearField.value = match[4];
    } else if (monthYearRangePattern.test(periodStr)) {
      // Month range same year: "Jan-Dec 2024"
      const match = periodStr.match(monthYearRangePattern);
      periodTypeSelect.value = 'month-range';
      const startMonthSelect = document.getElementById('modal-start-month');
      const startMonthYearField = document.getElementById('modal-start-month-year');
      const endMonthSelect = document.getElementById('modal-end-month');
      const endMonthYearField = document.getElementById('modal-end-month-year');

      if (startMonthSelect) startMonthSelect.value = monthToNumber[match[1]];
      if (startMonthYearField) startMonthYearField.value = match[3];
      if (endMonthSelect) endMonthSelect.value = monthToNumber[match[2]];
      if (endMonthYearField) endMonthYearField.value = match[3];
    } else if (monthPattern.test(periodStr)) {
      // Single month: "Jan 2024"
      const match = periodStr.match(monthPattern);
      periodTypeSelect.value = 'month-range';
      const startMonthSelect = document.getElementById('modal-start-month');
      const startMonthYearField = document.getElementById('modal-start-month-year');
      const endMonthSelect = document.getElementById('modal-end-month');
      const endMonthYearField = document.getElementById('modal-end-month-year');

      if (startMonthSelect) startMonthSelect.value = monthToNumber[match[1]];
      if (startMonthYearField) startMonthYearField.value = match[2];
      if (endMonthSelect) endMonthSelect.value = monthToNumber[match[1]];
      if (endMonthYearField) endMonthYearField.value = match[2];
    }

    // Toggle fields to show the correct input section
    togglePeriodFields();

    // Validate the parsed dates
    validateDateRanges();

    // Generate the period name to populate the hidden field
    generatePeriodName();
  }

  // Initialize upload button visibility based on existing documents
  function initializeUploadButtonVisibility() {
    document.querySelectorAll('.document-upload-btn').forEach(btn => {
      const fieldId = btn.dataset.fieldId;
      const maxDocuments = btn.dataset.maxDocuments ? parseInt(btn.dataset.maxDocuments) : null;

      if (!maxDocuments) return; // No limit, button always visible

      // Get the field container
      const fieldContainer = btn.closest('.form-item-block, .bg-gray-50');
      if (!fieldContainer) return;

      // Count existing documents
      const existingDocsCount = fieldContainer.querySelectorAll('.bg-green-100.border-green-400').length;

      console.log(`Field ${fieldId}: ${existingDocsCount} existing docs, max=${maxDocuments}`);

      // Hide button if we're at or over the limit
      if (existingDocsCount >= maxDocuments) {
        if (btn.parentElement) {
          btn.parentElement.style.display = 'none';
          console.log(`Hiding upload button for field ${fieldId} (at max capacity: ${existingDocsCount}/${maxDocuments})`);
        }
      }
    });
  }

  // Run initialization after a short delay to ensure DOM is ready
  setTimeout(initializeUploadButtonVisibility, 100);

  // Open modal when document upload button is clicked
  document.addEventListener('click', (e) => {
    const btn = e.target.closest('.document-upload-btn');
    if (!btn) return;

    currentFieldId = btn.dataset.fieldId;
    currentFieldLabel = btn.dataset.fieldLabel;
    currentIsRequired = btn.dataset.isRequired === 'true';
    currentHasExisting = btn.dataset.hasExisting === 'true';
    currentDocumentId = null;
    isEditMode = false;

    // Parse field configuration
    let fieldConfig = {};
    try {
      if (btn.dataset.fieldConfig) {
        fieldConfig = JSON.parse(btn.dataset.fieldConfig);
      }
    } catch (e) {
      console.error('Failed to parse field config:', e);
    }

    // Store config for later use
    const configInput = document.getElementById('modal-field-config');
    if (configInput) {
      configInput.value = JSON.stringify(fieldConfig);
    }

    // Check if maximum documents limit is reached before opening modal
    const maxDocuments = getMaxDocumentsForField(currentFieldId);
    const currentCount = getCurrentDocumentCount(currentFieldId);

    if (maxDocuments && currentCount >= maxDocuments) {
      const msg = `Maximum of ${maxDocuments} document(s) allowed for this field. You have already reached the limit.`;
      if (window.showAlert) window.showAlert(msg, 'warning');
      else console.warn(msg);
      return;
    }

    if (modalTitle) modalTitle.textContent = currentHasExisting ? t.replaceLabel : t.uploadLabel;
    if (fieldNameDisplay) fieldNameDisplay.textContent = currentFieldLabel || '';

    // Reset file input and UI
    if (modalFileInput) {
      modalFileInput.value = '';
      updateFileUploadBox(null);
    }

    // Reset language dropdown
    const languageSelect = document.getElementById('modal-document-language');
    if (languageSelect) {
      languageSelect.value = '';
    }

    // Reset document ID
    const documentIdInput = document.getElementById('modal-document-id');
    if (documentIdInput) {
      documentIdInput.value = '';
    }

    // Configure field visibility based on field config
    configureModalFields(fieldConfig);

    // Update max documents info display
    const maxDocumentsInfo = document.getElementById('modal-max-documents-info');
    if (maxDocumentsInfo) {
      if (maxDocuments && maxDocuments > 0) {
        maxDocumentsInfo.textContent = ` • ${t.maxDocumentsAllowed}: ${maxDocuments}`;
        maxDocumentsInfo.style.display = 'inline';
      } else {
        maxDocumentsInfo.textContent = '';
        maxDocumentsInfo.style.display = 'none';
      }
    }

    // Hide current document info in upload mode
    hideCurrentDocumentInfo();

    if (confirmUploadBtn) confirmUploadBtn.disabled = true;

    openModal();
  });

  // Handle edit document button clicks
  document.addEventListener('click', (e) => {
    const editBtn = e.target.closest('.edit-document-btn');
    if (!editBtn) return;

    e.preventDefault();
    e.stopPropagation();

    currentDocumentId = editBtn.dataset.docId;

    // Check if document is still pending (not yet saved to server)
    if (currentDocumentId === 'pending') {
      const msg = t.documentPendingSave || 'Please save the form first before editing this document.';
      window.showAlert(msg, 'warning');
      return;
    }

    // Validate document ID is a valid numeric ID
    if (!currentDocumentId || !currentDocumentId.match(/^[0-9]+$/)) {
      const msg = t.invalidDocumentId || 'Unable to edit: document ID is invalid. Please refresh the page and try again.';
      window.showAlert(msg, 'error');
      return;
    }

    currentFieldId = editBtn.dataset.fieldId;
    currentFieldLabel = editBtn.dataset.fieldLabel;
    currentIsRequired = false; // Not required for editing
    currentHasExisting = true;
    isEditMode = true;

    // Parse field configuration
    let fieldConfig = {};
    try {
      if (editBtn.dataset.fieldConfig) {
        fieldConfig = JSON.parse(editBtn.dataset.fieldConfig);
      }
    } catch (e) {
      console.error('Failed to parse field config:', e);
    }

    // Store config for later use
    const configInput = document.getElementById('modal-field-config');
    if (configInput) {
      configInput.value = JSON.stringify(fieldConfig);
    }

    if (modalTitle) modalTitle.textContent = t.editLabel;
    if (fieldNameDisplay) fieldNameDisplay.textContent = currentFieldLabel || '';

    // Set document ID
    const documentIdInput = document.getElementById('modal-document-id');
    if (documentIdInput) {
      documentIdInput.value = currentDocumentId;
    }

    // Configure modal fields based on config
    configureModalFields(fieldConfig);

    // Update max documents info display
    const maxDocuments = getMaxDocumentsForField(currentFieldId);
    const maxDocumentsInfo = document.getElementById('modal-max-documents-info');
    if (maxDocumentsInfo) {
      if (maxDocuments && maxDocuments > 0) {
        maxDocumentsInfo.textContent = ` • ${t.maxDocumentsAllowed}: ${maxDocuments}`;
        maxDocumentsInfo.style.display = 'inline';
      } else {
        maxDocumentsInfo.textContent = '';
        maxDocumentsInfo.style.display = 'none';
      }
    }

    // Reset file input for edit mode
    if (modalFileInput) {
      modalFileInput.value = '';
    }

    // Show current document info in edit mode
    showCurrentDocumentInfo(editBtn.dataset.filename || 'Unknown file');

    // Set language dropdown to current value
    const languageSelect = document.getElementById('modal-document-language');
    if (languageSelect) {
      languageSelect.value = editBtn.dataset.language || '';
    }

    // Set document type if available and visible
    const documentTypeSelect = document.getElementById('modal-document-type');
    if (documentTypeSelect && editBtn.dataset.documentType) {
      documentTypeSelect.value = editBtn.dataset.documentType;
    }

    // Set year/period if available and visible
    if (editBtn.dataset.year && editBtn.dataset.year !== 'None') {
      parseAndPopulatePeriod(editBtn.dataset.year);
    }

    // Set public checkbox if available and visible
    const isPublicCheckbox = document.getElementById('modal-is-public');
    if (isPublicCheckbox && editBtn.dataset.isPublic) {
      isPublicCheckbox.checked = editBtn.dataset.isPublic === 'true';
    }

    // Enable/disable upload button for edit mode based on required fields
    if (confirmUploadBtn) {
      confirmUploadBtn.disabled = false;
      validateUploadForm();
    }

    openModal();
  });

  // Helper function to mark document for deletion
  function markDocumentForDeletion(docId, docElement, fieldId) {
    // Find the hidden input for this document
    const hiddenInput = document.getElementById(`delete_document_hidden_${docId}`);
    if (!hiddenInput) {
      console.error(`Hidden input not found for document ${docId}`);
      return;
    }

    // Set the hidden input to "true"
    hiddenInput.value = 'true';

    // Store reference for cancel functionality
    documentsMarkedForDeletion[docId] = {
      element: docElement,
      fieldId: fieldId,
      hiddenInput: hiddenInput
    };

    // Change visual appearance to show "will be deleted"
    docElement.classList.remove('bg-green-100', 'border-green-400', 'text-green-700');
    docElement.classList.add('bg-red-50', 'border-red-300', 'text-red-700', 'opacity-75');

    // Ensure container uses flex-col layout
    if (!docElement.classList.contains('flex-col')) {
      docElement.classList.add('flex-col');
      docElement.classList.remove('flex', 'items-center', 'justify-between');
    }

    // Find the info paragraph (upload info) - it could be a sibling or already inside
    let uploadInfoP = docElement.querySelector('p.text-xs');
    if (!uploadInfoP) {
      // Check if it's a sibling
      uploadInfoP = docElement.nextElementSibling;
      if (uploadInfoP && uploadInfoP.classList.contains('text-xs') && (uploadInfoP.classList.contains('text-gray-600') || uploadInfoP.classList.contains('text-green-600'))) {
        // Move it inside the docElement
        uploadInfoP.classList.remove('text-gray-600', 'text-green-600', 'mb-3');
        uploadInfoP.classList.add('text-red-600', 'mt-1', 'ml-8');
        uploadInfoP.style.marginTop = '0.25rem';
        uploadInfoP.style.marginLeft = '2rem';
        uploadInfoP.style.marginBottom = '0';
        docElement.appendChild(uploadInfoP);
      }
    } else if (uploadInfoP.parentElement === docElement) {
      // Already inside, just update styling
      uploadInfoP.classList.remove('text-green-600');
      uploadInfoP.classList.add('text-red-600');
    } else {
      // It's a sibling, move it inside
      uploadInfoP.classList.remove('text-gray-600', 'text-green-600', 'mb-3');
      uploadInfoP.classList.add('text-red-600', 'mt-1', 'ml-8');
      uploadInfoP.style.marginTop = '0.25rem';
      uploadInfoP.style.marginLeft = '2rem';
      uploadInfoP.style.marginBottom = '0';
      docElement.appendChild(uploadInfoP);
    }

    // Add "Will be deleted on save" message inside the container
    let deleteMessage = docElement.querySelector('.delete-message');
    if (!deleteMessage) {
      deleteMessage = document.createElement('div');
      deleteMessage.className = 'delete-message text-xs text-red-600 mt-1 ml-8 flex items-center gap-2';
      deleteMessage.style.marginTop = '0.25rem';
      deleteMessage.style.marginLeft = '2rem';
      deleteMessage.style.marginBottom = '0';
      const icon = document.createElement('i');
      icon.className = 'fas fa-exclamation-triangle';
      deleteMessage.appendChild(icon);
      deleteMessage.appendChild(document.createTextNode('Will be deleted when you save the form.'));

      // Add inside the docElement, after the upload info
      if (uploadInfoP && uploadInfoP.parentElement === docElement) {
        uploadInfoP.parentElement.insertBefore(deleteMessage, uploadInfoP.nextSibling);
      } else {
        docElement.appendChild(deleteMessage);
      }
    }

    // Hide edit button, show cancel button
    const editBtn = docElement.querySelector('.edit-document-btn');
    const deleteBtn = docElement.querySelector('.delete-document-btn');

    if (editBtn) {
      editBtn.style.display = 'none';
    }

    if (deleteBtn) {
      deleteBtn.style.display = 'none';

      // Add cancel button
      let cancelBtn = docElement.querySelector('.cancel-delete-btn');
      if (!cancelBtn) {
        cancelBtn = document.createElement('button');
        cancelBtn.type = 'button';
        cancelBtn.className = 'cancel-delete-btn text-blue-600 hover:text-blue-800 flex-shrink-0';
        cancelBtn.dataset.docId = docId;
        cancelBtn.title = 'Cancel deletion';
        const cancelIcon = document.createElement('i');
        cancelIcon.className = 'fas fa-undo';
        cancelBtn.appendChild(cancelIcon);

        // Insert cancel button where delete button was
        const actionsDiv = deleteBtn.parentElement;
        if (actionsDiv) {
          actionsDiv.appendChild(cancelBtn);
        }
      }
    }

    // Marking for deletion should immediately free up an upload slot in the UI (if under max)
    const fieldContainer = docElement.closest('.form-item-block, .bg-gray-50');
    updateUploadButtonVisibility(fieldContainer, fieldId);
  }

  // Helper function to cancel document deletion
  function cancelDocumentDeletion(docId) {
    const deletionInfo = documentsMarkedForDeletion[docId];
    if (!deletionInfo) return;

    const { element, hiddenInput, fieldId } = deletionInfo;

    // If cancelling would exceed max docs (because another doc is queued), block cancel
    const maxDocuments = fieldId ? getMaxDocumentsForField(fieldId) : null;
    if (maxDocuments) {
      const currentCount = getCurrentDocumentCount(fieldId); // excludes this red doc
      if (currentCount + 1 > maxDocuments) {
        const msg = (t.errorCancelDeletion || '').replace('%(max)s', String(maxDocuments));
        if (window.showAlert) window.showAlert(msg, 'warning');
        else console.warn(msg);
        return;
      }
    }

    // Reset hidden input
    hiddenInput.value = 'false';

    // Restore visual appearance
    element.classList.remove('bg-red-50', 'border-red-300', 'text-red-700', 'opacity-75');
    element.classList.add('bg-green-100', 'border-green-400', 'text-green-700');

    // Remove delete message (inside the element)
    const deleteMessage = element.querySelector('.delete-message');
    if (deleteMessage) {
      deleteMessage.remove();
    }

    // Restore upload info styling if it's inside
    const uploadInfoP = element.querySelector('p.text-xs');
    if (uploadInfoP && uploadInfoP.parentElement === element) {
      // If it was moved from outside, restore and move back
      if (uploadInfoP.classList.contains('text-red-600')) {
        uploadInfoP.classList.remove('text-red-600', 'ml-8');
        uploadInfoP.classList.add('text-green-600', 'ml-8');
        uploadInfoP.style.marginTop = '0.25rem';
        uploadInfoP.style.marginLeft = '2rem';
      }
      // Keep it inside - it should stay inside for consistency
    }

    // Show edit/delete buttons, hide cancel button
    const editBtn = element.querySelector('.edit-document-btn');
    const deleteBtn = element.querySelector('.delete-document-btn');
    const cancelBtn = element.querySelector('.cancel-delete-btn');

    if (editBtn) {
      editBtn.style.display = '';
    }
    if (deleteBtn) {
      deleteBtn.style.display = '';
    }
    if (cancelBtn) {
      cancelBtn.remove();
    }

    // Remove from tracking
    delete documentsMarkedForDeletion[docId];

    // Cancelling deletion can put us back at max capacity, so update upload button visibility
    const fieldContainer = element.closest('.form-item-block, .bg-gray-50');
    updateUploadButtonVisibility(fieldContainer, fieldId);
  }

  // Handle delete document button clicks
  document.addEventListener('click', (e) => {
    const deleteBtn = e.target.closest('.delete-document-btn');
    if (!deleteBtn) return;

    e.preventDefault();
    e.stopPropagation();

    const docId = deleteBtn.dataset.docId;
    if (!docId) {
      console.error('No document ID found for delete button');
      return;
    }

    // Validate document ID format
    if (!docId || !docId.match(/^[0-9]+$/)) {
      console.error('Invalid document ID format');
      return;
    }

    // Check if already marked for deletion
    if (documentsMarkedForDeletion[docId]) {
      return; // Already marked, ignore click
    }

    // Show confirmation dialog
    const docElement = deleteBtn.closest('.bg-green-100.border-green-400');
    const filenameLink = docElement?.querySelector('a');
    const filename = filenameLink?.textContent?.trim() || 'this document';

    const confirmMessage = `Are you sure you want to delete "${filename}"? The document will be deleted when you save the form.`;

    // Find field container (needed inside confirm callback)
    const fieldContainer = deleteBtn.closest('.form-item-block, .bg-gray-50');
    const uploadBtn = fieldContainer?.querySelector('.document-upload-btn');
    const fieldId = uploadBtn?.dataset.fieldId;

    // Use custom confirmation modal (no native confirm)
    const onConfirm = () => markDocumentForDeletion(docId, docElement, fieldId);
    const onCancel = () => { /* no-op */ };

    if (window.showDangerConfirmation) {
      window.showDangerConfirmation(confirmMessage, onConfirm, onCancel, 'Delete', 'Cancel', 'Confirm Delete');
    } else if (window.showConfirmation) {
      window.showConfirmation(confirmMessage, onConfirm, onCancel, 'Delete', 'Cancel', 'Confirm Delete');
    } else {
      // Should not happen (confirm-dialogs.js loaded globally), but never use native confirm
      console.warn('Confirmation dialog not available:', confirmMessage);
    }
  });

  // Handle cancel deletion button clicks
  document.addEventListener('click', (e) => {
    const cancelBtn = e.target.closest('.cancel-delete-btn');
    if (!cancelBtn) return;

    e.preventDefault();
    e.stopPropagation();

    const docId = cancelBtn.dataset.docId;
    if (!docId) return;

    cancelDocumentDeletion(docId);
  });

  // Wire modal open/close (Escape, backdrop, close buttons) via ModalUtils
  const modalController = (window.ModalUtils && window.ModalUtils.makeModal(modal, {
    closeSelector: '.close-modal-btn',
    onClose: () => {
      hideCurrentDocumentInfo();
      clearDateValidationErrors();
      if (modalFileInput) {
        delete modalFileInput.dataset.changeListenerAttached;
        modalFileInput.value = '';
        updateFileUploadBox(null);
      }
    }
  })) || { openModal: () => modal.classList.remove('hidden'), closeModal: () => modal.classList.add('hidden') };

  // Store original text on initialization
  const fileUploadBox = modal.querySelector('.file-upload-box');
  const originalTextElement = fileUploadBox?.querySelector('p');
  const originalText = originalTextElement ? originalTextElement.textContent : 'Click or drag document here to upload';
  if (originalTextElement) {
    originalTextElement.dataset.originalText = originalText;
  }

  // Update file upload box UI when file is selected
  function updateFileUploadBox(file) {
    const fileUploadBox = modal.querySelector('.file-upload-box');
    if (!fileUploadBox) return;

    const icon = fileUploadBox.querySelector('i');
    const text = fileUploadBox.querySelector('p');
    const dropZone = modal.querySelector('.file-upload-wrapper');

    if (file) {
      // Update icon to file icon
      if (icon) {
        icon.classList.remove('fa-cloud-upload-alt', 'text-gray-400');
        icon.classList.add('fa-file-alt', 'text-green-600');
      }

      // Update text to show filename
      if (text) {
        text.textContent = file.name;
        text.classList.remove('text-gray-500');
        text.classList.add('text-green-700', 'font-medium');
      }

      // Update border to indicate file selected
      if (dropZone) {
        dropZone.classList.remove('border-gray-300');
        dropZone.classList.add('border-green-500', 'bg-green-50');
      }
    } else {
      // Reset to default state
      if (icon) {
        icon.classList.remove('fa-file-alt', 'text-green-600');
        icon.classList.add('fa-cloud-upload-alt', 'text-gray-400');
      }

      if (text) {
        // Restore original text
        text.textContent = text.dataset.originalText || originalText;
        text.classList.remove('text-green-700', 'font-medium');
        text.classList.add('text-gray-500');
      }

      if (dropZone) {
        dropZone.classList.remove('border-green-500', 'bg-green-50');
        dropZone.classList.add('border-gray-300');
      }
    }
  }

  // Enable/disable upload button based on file selection and validate
  if (modalFileInput) {
    modalFileInput.addEventListener('change', function() {
      const file = this.files && this.files[0];
      updateFileUploadBox(file);
      validateUploadForm();
    });

    // Drag and drop handling
    const dropZone = modal.querySelector('.file-upload-wrapper');
    if (dropZone) {
      ['dragenter', 'dragover', 'dragleave', 'drop'].forEach(eventName => {
        dropZone.addEventListener(eventName, function(e) {
          e.preventDefault();
          e.stopPropagation();
        }, false);
      });

      ['dragenter', 'dragover'].forEach(eventName => {
        dropZone.addEventListener(eventName, function() {
          dropZone.classList.add('border-blue-500', 'bg-blue-50');
        }, false);
      });

      ['dragleave', 'drop'].forEach(eventName => {
        dropZone.addEventListener(eventName, function() {
          dropZone.classList.remove('border-blue-500', 'bg-blue-50');
        }, false);
      });

      dropZone.addEventListener('drop', function(e) {
        const dt = e.dataTransfer;
        const file = dt.files[0];

        if (file) {
          const allowedExtensions = ['.pdf', '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx', '.txt'];
          const fileName = file.name.toLowerCase();
          const isValidFile = allowedExtensions.some(ext => fileName.endsWith(ext));

          if (isValidFile) {
            const dataTransfer = new DataTransfer();
            dataTransfer.items.add(file);
            modalFileInput.files = dataTransfer.files;
            modalFileInput.dispatchEvent(new Event('change', { bubbles: true }));
          }
        }
      }, false);
    }
  }

  // Add language dropdown validation
  const languageSelect = document.getElementById('modal-document-language');
  if (languageSelect) {
    languageSelect.addEventListener('change', validateUploadForm);
  }

  function validateUploadForm() {
    const file = modalFileInput.files && modalFileInput.files[0];
    const selectedLanguage = languageSelect ? languageSelect.value : '';
    const languageSection = languageSelect?.closest('div');
    const isLanguageVisible = languageSection && !languageSection.classList.contains('hidden');
    const maxSize = 25 * 1024 * 1024; // 25MB
    const allowed = ['.pdf', '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx', '.txt'];
    const dangerousExtensions = ['.exe', '.bat', '.cmd', '.com', '.pif', '.scr', '.vbs', '.js', '.jar', '.php', '.asp', '.jsp', '.py', '.rb', '.sh', '.ps1'];

    // Clear any previous validation message when user makes changes
    clearValidationMessage();

    // In edit mode, file is optional
    if (isEditMode) {
      if (file) {
        if (file.size > maxSize) {
          if (window.showAlert) window.showAlert(t.errorSize, 'error');
          else console.warn(t.errorSize);
          modalFileInput.value = '';
          confirmUploadBtn.disabled = true;
          return;
        }

        const ext = '.' + file.name.split('.').pop().toLowerCase();

        // Check for dangerous file extensions
        if (dangerousExtensions.includes(ext)) {
          const msg = 'Security Error: This file type is not permitted for security reasons.';
          if (window.showAlert) window.showAlert(msg, 'error');
          else console.warn(msg);
          modalFileInput.value = '';
          confirmUploadBtn.disabled = true;
          return;
        }

        if (!allowed.includes(ext)) {
          if (window.showAlert) window.showAlert(t.errorType, 'error');
          else console.warn(t.errorType);
          modalFileInput.value = '';
          confirmUploadBtn.disabled = true;
          return;
        }

        // Additional MIME type validation
        const allowedMimeTypes = [
          'application/pdf',
          'application/msword',
          'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
          'application/vnd.ms-excel',
          'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
          'application/vnd.ms-powerpoint',
          'application/vnd.openxmlformats-officedocument.presentationml.presentation',
          'text/plain'
        ];

        if (file.type && !allowedMimeTypes.includes(file.type)) {
          const msg = 'Security Error: File MIME type validation failed.';
          if (window.showAlert) window.showAlert(msg, 'error');
          else console.warn(msg);
          modalFileInput.value = '';
          confirmUploadBtn.disabled = true;
          return;
        }
      }

      // Require period value if year/period selector is enabled
      if (!ensurePeriodSelected(false)) {
        confirmUploadBtn.disabled = true;
        return;
      }

      // Enable button in edit mode (remaining validation happens on click)
      confirmUploadBtn.disabled = false;
      return;
    }

    // Upload mode - file is required, language validation happens on click
    if (!file) {
      confirmUploadBtn.disabled = true;
      return;
    }

    if (file.size > maxSize) {
      if (window.showAlert) window.showAlert(t.errorSize, 'error');
      else console.warn(t.errorSize);
      modalFileInput.value = '';
      confirmUploadBtn.disabled = true;
      return;
    }

    const ext = '.' + file.name.split('.').pop().toLowerCase();

    // Check for dangerous file extensions
    if (dangerousExtensions.includes(ext)) {
      const msg = 'Security Error: This file type is not permitted for security reasons.';
      if (window.showAlert) window.showAlert(msg, 'error');
      else console.warn(msg);
      modalFileInput.value = '';
      confirmUploadBtn.disabled = true;
      return;
    }

    if (!allowed.includes(ext)) {
      if (window.showAlert) window.showAlert(t.errorType, 'error');
      else console.warn(t.errorType);
      modalFileInput.value = '';
      confirmUploadBtn.disabled = true;
      return;
    }

    // Additional MIME type validation
    const allowedMimeTypes = [
      'application/pdf',
      'application/msword',
      'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
      'application/vnd.ms-excel',
      'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
      'application/vnd.ms-powerpoint',
      'application/vnd.openxmlformats-officedocument.presentationml.presentation',
      'text/plain'
    ];

    if (file.type && !allowedMimeTypes.includes(file.type)) {
      const msg = 'Security Error: File MIME type validation failed.';
      if (window.showAlert) window.showAlert(msg, 'error');
      else console.warn(msg);
      modalFileInput.value = '';
      confirmUploadBtn.disabled = true;
      return;
    }

    // Require period value if year/period selector is enabled
    if (!ensurePeriodSelected(false)) {
      confirmUploadBtn.disabled = true;
      return;
    }

    // Enable button when file is selected (language validation happens on click)
    confirmUploadBtn.disabled = false;
  }

  // Show validation message in modal
  function showValidationMessage(message) {
    clearValidationMessage();

    const languageSelect = document.getElementById('modal-document-language');
    if (!languageSelect || !languageSelect.parentElement) return;

    const messageDiv = document.createElement('div');
    messageDiv.className = 'validation-message mt-2 p-2 bg-red-50 border border-red-200 rounded text-sm text-red-700';
    const icon = document.createElement('i');
    icon.className = 'fas fa-exclamation-circle mr-1';
    messageDiv.appendChild(icon);
    messageDiv.appendChild(document.createTextNode(message));

    languageSelect.parentElement.appendChild(messageDiv);

    // Highlight the language dropdown
    languageSelect.classList.add('border-red-500', 'ring-2', 'ring-red-200');
    languageSelect.focus();
  }

  // Clear validation message
  function clearValidationMessage() {
    const existingMessages = modal.querySelectorAll('.validation-message');
    existingMessages.forEach(msg => msg.remove());

    // Remove highlight from language dropdown
    const languageSelect = document.getElementById('modal-document-language');
    if (languageSelect) {
      languageSelect.classList.remove('border-red-500', 'ring-2', 'ring-red-200');
    }
  }

  // Handle upload confirmation
  if (confirmUploadBtn) {
    confirmUploadBtn.addEventListener('click', function () {
      if (!currentFieldId) return;

      // Get field config
      const configInput = document.getElementById('modal-field-config');
      let fieldConfig = {};
      try {
        if (configInput && configInput.value) {
          fieldConfig = JSON.parse(configInput.value);
        }
      } catch (e) {
        console.error('Failed to parse field config:', e);
      }

      // Validate date ranges before proceeding
      if (!validateDateRanges()) {
        const msg = 'Please correct the date range errors before uploading.';
        if (window.showAlert) window.showAlert(msg, 'error');
        else console.warn(msg);
        return;
      }

      // If year/period selector is enabled, require a period value
      if (!ensurePeriodSelected(true)) {
        return;
      }

      // Get the language value
      const languageSelect = document.getElementById('modal-document-language');
      const selectedLanguage = languageSelect ? languageSelect.value : '';
      const languageSection = languageSelect?.closest('div');
      const isLanguageVisible = languageSection && !languageSection.classList.contains('hidden');

      // Validate language selection only if language field is visible
      if (isLanguageVisible && !selectedLanguage) {
        showValidationMessage('Please select a language for the document.');
        return;
      }

      // Clear validation message if language is selected or not required
      clearValidationMessage();

      if (isEditMode) {
        // Edit mode - update existing document
        if (!currentDocumentId) {
          const msg = 'Document ID not found for editing.';
          if (window.showAlert) window.showAlert(msg, 'error');
          else console.warn(msg);
          return;
        }

        // Create or get the hidden document ID input
        let hiddenDocumentIdInput = document.querySelector(`input[name="edit_document_id[${currentFieldId}]"]`);
        if (!hiddenDocumentIdInput) {
          hiddenDocumentIdInput = document.createElement('input');
          hiddenDocumentIdInput.type = 'hidden';
          hiddenDocumentIdInput.name = `edit_document_id[${currentFieldId}]`;
          document.getElementById('focalDataEntryForm').appendChild(hiddenDocumentIdInput);
        }

        // Create or get the hidden language input for editing
        let hiddenLanguageInput = document.querySelector(`input[name="edit_document_language[${currentFieldId}]"]`);
        if (!hiddenLanguageInput) {
          hiddenLanguageInput = document.createElement('input');
          hiddenLanguageInput.type = 'hidden';
          hiddenLanguageInput.name = `edit_document_language[${currentFieldId}]`;
          document.getElementById('focalDataEntryForm').appendChild(hiddenLanguageInput);
        }

        // Validate document ID format before setting
        if (!currentDocumentId || !currentDocumentId.match(/^[0-9]+$/)) {
          // This should rarely happen now since we validate early, but keep as fallback
          const msg = currentDocumentId === 'pending'
            ? (t.documentPendingSave || 'Please save the form first before editing this document.')
            : (t.invalidDocumentId || 'Unable to edit: document ID is invalid. Please refresh the page and try again.');
          if (window.showAlert) window.showAlert(msg, currentDocumentId === 'pending' ? 'warning' : 'error');
          else console.warn(msg);
          return;
        }

        // Set the document ID and language for editing (use 'en' as default if language field is hidden)
        hiddenDocumentIdInput.value = currentDocumentId;
        hiddenLanguageInput.value = selectedLanguage || 'en';

        // Handle file replacement if a new file is selected
        const file = modalFileInput.files && modalFileInput.files[0];
        if (file) {
          let hiddenFileInput = document.querySelector(`input[name="edit_document_file[${currentFieldId}]"]`);
          if (!hiddenFileInput) {
            hiddenFileInput = document.createElement('input');
            hiddenFileInput.type = 'file';
            hiddenFileInput.name = `edit_document_file[${currentFieldId}]`;
            hiddenFileInput.style.display = 'none';
            document.getElementById('focalDataEntryForm').appendChild(hiddenFileInput);
          }

          const dataTransfer = new DataTransfer();
          dataTransfer.items.add(file);
          hiddenFileInput.files = dataTransfer.files;
        }

        // Handle additional fields for editing (document type, year, public status)
        const documentType = document.getElementById('modal-document-type')?.value || '';
        const yearValue = document.getElementById('modal-year-value')?.value || '';
        const isPublic = document.getElementById('modal-is-public')?.checked || false;

        // Create or update hidden inputs for additional fields
        if (documentType) {
          let typeInput = document.querySelector(`input[name="edit_document_type[${currentFieldId}]"]`);
          if (!typeInput) {
            typeInput = document.createElement('input');
            typeInput.type = 'hidden';
            typeInput.name = `edit_document_type[${currentFieldId}]`;
            document.getElementById('focalDataEntryForm').appendChild(typeInput);
          }
          typeInput.value = documentType;
        }

        if (yearValue) {
          let yearInput = document.querySelector(`input[name="edit_document_year[${currentFieldId}]"]`);
          if (!yearInput) {
            yearInput = document.createElement('input');
            yearInput.type = 'hidden';
            yearInput.name = `edit_document_year[${currentFieldId}]`;
            document.getElementById('focalDataEntryForm').appendChild(yearInput);
          }
          yearInput.value = yearValue;
        }

        if (isPublic) {
          let publicInput = document.querySelector(`input[name="edit_document_is_public[${currentFieldId}]"]`);
          if (!publicInput) {
            publicInput = document.createElement('input');
            publicInput.type = 'hidden';
            publicInput.name = `edit_document_is_public[${currentFieldId}]`;
            document.getElementById('focalDataEntryForm').appendChild(publicInput);
          }
          publicInput.value = '1';
        }

        // Show visual feedback
        showDocumentPendingFeedback(currentFieldId, file ? file.name : null, selectedLanguage);
      } else {
        // Upload mode - create new document
        if (!modalFileInput.files || modalFileInput.files.length === 0) return;

        const file = modalFileInput.files[0];

        // Check max documents limit
        const maxDocuments = getMaxDocumentsForField(currentFieldId);
        const currentCount = getCurrentDocumentCount(currentFieldId);

        if (maxDocuments && currentCount >= maxDocuments) {
          const msg = `Maximum of ${maxDocuments} document(s) allowed for this field.`;
          if (window.showAlert) window.showAlert(msg, 'warning');
          else console.warn(msg);
          return;
        }

        // Initialize queue for this field if needed
        if (!queuedDocuments[currentFieldId]) {
          queuedDocuments[currentFieldId] = [];
        }

        // Create unique identifier for this queued document
        const queueId = Date.now() + '_' + Math.random().toString(36).substr(2, 9);

        // Create hidden file input for this specific queued document
        const hiddenFileInput = document.createElement('input');
        hiddenFileInput.type = 'file';
        hiddenFileInput.name = `field_value[${currentFieldId}]`;
        hiddenFileInput.style.display = 'none';
        hiddenFileInput.dataset.queueId = queueId;
        if (currentIsRequired && !currentHasExisting && queuedDocuments[currentFieldId].length === 0) {
          hiddenFileInput.required = true;
        }
        document.getElementById('focalDataEntryForm').appendChild(hiddenFileInput);

        // Create hidden language input for this specific queued document
        const hiddenLanguageInput = document.createElement('input');
        hiddenLanguageInput.type = 'hidden';
        hiddenLanguageInput.name = `field_language[${currentFieldId}]`;
        hiddenLanguageInput.dataset.queueId = queueId;
        document.getElementById('focalDataEntryForm').appendChild(hiddenLanguageInput);

        // Transfer the file from modal to hidden input
        const dataTransfer = new DataTransfer();
        dataTransfer.items.add(file);
        hiddenFileInput.files = dataTransfer.files;

        // Set the language value (use 'en' as default if language field is hidden)
        hiddenLanguageInput.value = selectedLanguage || 'en';

        // Get additional field values from modal
        const documentType = document.getElementById('modal-document-type')?.value || '';
        const yearValue = document.getElementById('modal-year-value')?.value || '';
        const isPublic = document.getElementById('modal-is-public')?.checked || false;

        // Create hidden inputs for additional fields if they have values
        const additionalInputs = [];

        if (documentType) {
          const typeInput = document.createElement('input');
          typeInput.type = 'hidden';
          typeInput.name = `field_document_type[${currentFieldId}]`;
          typeInput.value = documentType;
          typeInput.dataset.queueId = queueId;
          document.getElementById('focalDataEntryForm').appendChild(typeInput);
          additionalInputs.push(typeInput);
        }

        if (yearValue) {
          const yearInput = document.createElement('input');
          yearInput.type = 'hidden';
          yearInput.name = `field_year[${currentFieldId}]`;
          yearInput.value = yearValue;
          yearInput.dataset.queueId = queueId;
          document.getElementById('focalDataEntryForm').appendChild(yearInput);
          additionalInputs.push(yearInput);
        }

        if (isPublic) {
          const publicInput = document.createElement('input');
          publicInput.type = 'hidden';
          publicInput.name = `field_is_public[${currentFieldId}]`;
          publicInput.value = '1';
          publicInput.dataset.queueId = queueId;
          document.getElementById('focalDataEntryForm').appendChild(publicInput);
          additionalInputs.push(publicInput);
        }

        // Add to queue
        queuedDocuments[currentFieldId].push({
          queueId: queueId,
          file: file,
          fileName: file.name,
          language: selectedLanguage,
          documentType: documentType,
          year: yearValue,
          isPublic: isPublic,
          hiddenFileInput: hiddenFileInput,
          hiddenLanguageInput: hiddenLanguageInput,
          additionalInputs: additionalInputs
        });

        // Show visual feedback for all queued documents
        showAllQueuedDocuments(currentFieldId);
      }

      closeModal();
    });
  }

  // Get max documents allowed for a field
  function getMaxDocumentsForField(fieldId) {
    const fieldContainer = document.querySelector(`[data-field-id="${fieldId}"]`)?.closest('.form-item-block, .bg-gray-50');
    if (!fieldContainer) return null;

    const uploadBtn = fieldContainer.querySelector('.document-upload-btn');
    if (!uploadBtn) return null;

    return uploadBtn.dataset.maxDocuments ? parseInt(uploadBtn.dataset.maxDocuments) : null;
  }

  // Get current document count (existing + queued, excluding marked for deletion)
  function getCurrentDocumentCount(fieldId) {
    const fieldContainer = document.querySelector(`[data-field-id="${fieldId}"]`)?.closest('.form-item-block, .bg-gray-50');
    if (!fieldContainer) return 0;

    // Count existing uploaded documents - look for green document containers only
    // Don't count red ones (marked for deletion) as they will be removed on save
    const existingDocs = fieldContainer.querySelectorAll('.bg-green-100.border-green-400').length;

    // Count queued documents
    const queuedCount = queuedDocuments[fieldId] ? queuedDocuments[fieldId].length : 0;

    console.log(`Document count for field ${fieldId}: existing=${existingDocs}, queued=${queuedCount}, total=${existingDocs + queuedCount}, max allowed=${getMaxDocumentsForField(fieldId)}`);

    return existingDocs + queuedCount;
  }

  // Remove a queued document
  function removeQueuedDocument(fieldId, queueId) {
    if (!queuedDocuments[fieldId]) return;

    // Find and remove from queue
    const index = queuedDocuments[fieldId].findIndex(doc => doc.queueId === queueId);
    if (index > -1) {
      const doc = queuedDocuments[fieldId][index];

      // Remove hidden inputs from form
      if (doc.hiddenFileInput && doc.hiddenFileInput.parentNode) {
        doc.hiddenFileInput.parentNode.removeChild(doc.hiddenFileInput);
      }
      if (doc.hiddenLanguageInput && doc.hiddenLanguageInput.parentNode) {
        doc.hiddenLanguageInput.parentNode.removeChild(doc.hiddenLanguageInput);
      }

      // Remove additional inputs (document type, year, public)
      if (doc.additionalInputs && doc.additionalInputs.length > 0) {
        doc.additionalInputs.forEach(input => {
          if (input && input.parentNode) {
            input.parentNode.removeChild(input);
          }
        });
      }

      // Remove from queue
      queuedDocuments[fieldId].splice(index, 1);

      // Update display (this will also show the upload button again if we're now below the limit)
      showAllQueuedDocuments(fieldId);

      // Ensure button is shown if we're below the limit after removal
      const maxDocuments = getMaxDocumentsForField(fieldId);
      const currentCount = getCurrentDocumentCount(fieldId);
      const fieldContainer = document.querySelector(`[data-field-id="${fieldId}"]`)?.closest('.form-item-block, .bg-gray-50');
      if (fieldContainer) {
        const uploadBtn = fieldContainer.querySelector('.document-upload-btn');
        if (uploadBtn && uploadBtn.parentElement && (!maxDocuments || currentCount < maxDocuments)) {
          uploadBtn.parentElement.style.display = '';
          console.log(`Showing upload button again for field ${fieldId} (${currentCount}/${maxDocuments || '∞'})`);
        }
      }
    }
  }

  // Show all queued documents for a field
  function showAllQueuedDocuments(fieldId) {
    const fieldContainer = document.querySelector(`[data-field-id="${fieldId}"]`)?.closest('.form-item-block, .bg-gray-50');
    if (!fieldContainer) return;

    // Remove old feedback divs
    fieldContainer.querySelectorAll('.document-pending-feedback').forEach(el => el.remove());
    fieldContainer.querySelectorAll('.document-queue-container').forEach(el => el.remove());

    // If no queued documents, reset button state
    if (!queuedDocuments[fieldId] || queuedDocuments[fieldId].length === 0) {
      const uploadBtn = fieldContainer.querySelector('.document-upload-btn');
      if (uploadBtn && !uploadBtn.dataset.hasExisting) {
        setEmptyState(uploadBtn);
      }
      return;
    }

    // Check if we've reached the maximum
    const maxDocuments = getMaxDocumentsForField(fieldId);
    const currentCount = getCurrentDocumentCount(fieldId);

    // Update button to show plus icon
    const uploadBtn = fieldContainer.querySelector('.document-upload-btn');
    if (uploadBtn) {
      // Hide the button if maximum is reached
      if (maxDocuments && currentCount >= maxDocuments) {
        console.log(`Max documents reached for field ${fieldId}, hiding upload button`);
        if (uploadBtn.parentElement) {
          uploadBtn.parentElement.style.display = 'none';
        }
      } else {
        // Show the button and update styling
        if (uploadBtn.parentElement) {
          uploadBtn.parentElement.style.display = '';
        }

        setHasDocsState(uploadBtn);
      }
    }

    // Create container for all queued documents
    const queueContainer = document.createElement('div');
    queueContainer.className = 'document-queue-container mb-2';

    queuedDocuments[fieldId].forEach((doc) => {
      const feedbackDiv = document.createElement('div');
      feedbackDiv.className = 'document-pending-feedback mb-2 p-3 bg-blue-50 border border-blue-200 rounded-md text-sm';
      feedbackDiv.dataset.queueId = doc.queueId;

      // Build feedback div using DOM construction
      const mainDiv = document.createElement('div');
      mainDiv.className = 'flex items-start justify-between gap-2';

      const leftDiv = document.createElement('div');
      leftDiv.className = 'flex items-start gap-2 flex-1 min-w-0';

      const clockIcon = document.createElement('i');
      clockIcon.className = 'fas fa-clock text-blue-600 mt-0.5 flex-shrink-0';

      const contentDiv = document.createElement('div');
      contentDiv.className = 'text-blue-800 min-w-0 flex-1';

      const queuedDiv = document.createElement('div');
      const queuedStrong = document.createElement('strong');
      queuedStrong.textContent = 'Queued: ';
      const filenameSpan = document.createElement('span');
      filenameSpan.className = 'filename break-words break-all';
      filenameSpan.textContent = doc.fileName;
      queuedDiv.appendChild(queuedStrong);
      queuedDiv.appendChild(filenameSpan);

      const badgesDiv = document.createElement('div');
      badgesDiv.className = 'mt-1';

      // Build metadata badges using DOM construction
      if (doc.language && doc.language !== 'en') {
        const langBadge = document.createElement('span');
        langBadge.className = 'language-badge ml-2 px-2 py-0.5 bg-blue-100 rounded text-xs whitespace-nowrap inline-block';
        langBadge.textContent = doc.language.toUpperCase();
        badgesDiv.appendChild(langBadge);
      } else if (doc.language === 'en') {
        const langBadge = document.createElement('span');
        langBadge.className = 'language-badge ml-2 px-2 py-0.5 bg-gray-100 text-gray-600 rounded text-xs whitespace-nowrap inline-block';
        langBadge.textContent = 'EN';
        badgesDiv.appendChild(langBadge);
      }

      if (doc.documentType) {
        const typeBadge = document.createElement('span');
        typeBadge.className = 'px-2 py-0.5 bg-purple-100 text-purple-700 rounded text-xs whitespace-nowrap inline-block';
        typeBadge.textContent = doc.documentType;
        badgesDiv.appendChild(document.createTextNode(' '));
        badgesDiv.appendChild(typeBadge);
      }

      if (doc.year) {
        const yearBadge = document.createElement('span');
        yearBadge.className = 'px-2 py-0.5 bg-green-100 text-green-700 rounded text-xs whitespace-nowrap inline-block';
        yearBadge.textContent = doc.year;
        badgesDiv.appendChild(document.createTextNode(' '));
        badgesDiv.appendChild(yearBadge);
      }

      if (doc.isPublic) {
        const publicBadge = document.createElement('span');
        publicBadge.className = 'px-2 py-0.5 bg-amber-100 text-amber-700 rounded text-xs whitespace-nowrap inline-block';
        const globeIcon = document.createElement('i');
        globeIcon.className = 'fas fa-globe';
        publicBadge.appendChild(globeIcon);
        publicBadge.appendChild(document.createTextNode(' Public'));
        badgesDiv.appendChild(document.createTextNode(' '));
        badgesDiv.appendChild(publicBadge);
      }

      contentDiv.appendChild(queuedDiv);
      contentDiv.appendChild(badgesDiv);
      leftDiv.appendChild(clockIcon);
      leftDiv.appendChild(contentDiv);

      const removeBtn = document.createElement('button');
      removeBtn.type = 'button';
      removeBtn.className = 'remove-queued-doc text-red-600 hover:text-red-800 flex-shrink-0';
      removeBtn.setAttribute('data-queue-id', doc.queueId);
      removeBtn.setAttribute('title', 'Remove');
      const removeIcon = document.createElement('i');
      removeIcon.className = 'fas fa-times';
      removeBtn.appendChild(removeIcon);

      mainDiv.appendChild(leftDiv);
      mainDiv.appendChild(removeBtn);

      const messageP = document.createElement('p');
      messageP.className = 'text-blue-600 text-xs mt-1 ml-6';
      messageP.textContent = 'Will be uploaded when you save the form.';

      feedbackDiv.appendChild(mainDiv);
      feedbackDiv.appendChild(messageP);
      queueContainer.appendChild(feedbackDiv);
    });

    // Insert before the upload button
    if (uploadBtn && uploadBtn.parentElement) {
      uploadBtn.parentElement.parentElement.insertBefore(queueContainer, uploadBtn.parentElement);
    }

    // Add event listeners for remove buttons
    queueContainer.querySelectorAll('.remove-queued-doc').forEach(btn => {
      btn.addEventListener('click', (e) => {
        e.preventDefault();
        const queueId = btn.dataset.queueId;
        removeQueuedDocument(fieldId, queueId);
      });
    });
  }

  // Helper function to show document pending upload feedback
  function showDocumentPendingFeedback(fieldId, filename, language) {
    // Find the document field container
    const fieldContainer = document.querySelector(`[data-field-id="${fieldId}"]`)?.closest('.form-item-block, .bg-gray-50');
    if (!fieldContainer) return;

    // Change the upload button to "+" style
    const uploadBtn = fieldContainer.querySelector('.document-upload-btn');
    if (uploadBtn) {
      setHasDocsState(uploadBtn);
    }

    // Check if feedback already exists
    let feedbackDiv = fieldContainer.querySelector('.document-pending-feedback');
    if (!feedbackDiv) {
      feedbackDiv = document.createElement('div');
      feedbackDiv.className = 'document-pending-feedback mb-2 p-3 bg-blue-50 border border-blue-200 rounded-md text-sm';

      const mainDiv = document.createElement('div');
      mainDiv.className = 'flex items-center gap-2';

      const clockIcon = document.createElement('i');
      clockIcon.className = 'fas fa-clock text-blue-600';

      const contentSpan = document.createElement('span');
      contentSpan.className = 'text-blue-800';
      const strong = document.createElement('strong');
      strong.textContent = 'Document queued: ';
      const filenameSpan = document.createElement('span');
      filenameSpan.className = 'filename';
      const langBadge = document.createElement('span');
      langBadge.className = 'language-badge ml-2 px-2 py-0.5 bg-blue-100 rounded text-xs';

      contentSpan.appendChild(strong);
      contentSpan.appendChild(filenameSpan);
      contentSpan.appendChild(document.createTextNode(' '));
      contentSpan.appendChild(langBadge);

      mainDiv.appendChild(clockIcon);
      mainDiv.appendChild(contentSpan);

      const messageP = document.createElement('p');
      messageP.className = 'text-blue-600 text-xs mt-1 ml-6';
      messageP.textContent = 'Will be uploaded when you save the form.';

      feedbackDiv.appendChild(mainDiv);
      feedbackDiv.appendChild(messageP);

      // Insert before the upload button (so it appears above the button, below any existing documents)
      if (uploadBtn && uploadBtn.parentElement) {
        uploadBtn.parentElement.parentElement.insertBefore(feedbackDiv, uploadBtn.parentElement);
      }
    }

    // Update the feedback
    const filenameSpan = feedbackDiv.querySelector('.filename');
    const languageBadge = feedbackDiv.querySelector('.language-badge');
    if (filenameSpan) filenameSpan.textContent = filename || 'Document';
    if (languageBadge) languageBadge.textContent = language ? language.toUpperCase() : 'EN';
  }

  function openModal() {
    modalController.openModal();
    if (modalFileInput) modalFileInput.focus();
  }

  function closeModal() {
    modalController.closeModal();
  }

  // Show current document info (for edit mode)
  function showCurrentDocumentInfo(filename) {
    const currentDocInfo = document.getElementById('current-document-info');
    const currentDocFilename = document.getElementById('current-document-filename');

    if (currentDocInfo && currentDocFilename && filename) {
      currentDocFilename.textContent = filename;
      currentDocInfo.classList.remove('hidden');

      // Add listener to file input to show replacement feedback
      if (modalFileInput && !modalFileInput.dataset.changeListenerAttached) {
        modalFileInput.addEventListener('change', function() {
          if (this.files && this.files[0]) {
            // Update the current document info to show replacement
            currentDocInfo.classList.remove('bg-blue-50', 'border-blue-200');
            currentDocInfo.classList.add('bg-amber-50', 'border-amber-300');

            const iconEl = currentDocInfo.querySelector('i');
            if (iconEl) {
              iconEl.classList.remove('text-blue-600');
              iconEl.classList.add('text-amber-600');
            }

            const titleEl = currentDocInfo.querySelector('.text-blue-900');
            if (titleEl) {
              titleEl.classList.remove('text-blue-900');
              titleEl.classList.add('text-amber-900');
              titleEl.textContent = 'Will Replace:';
            }

            currentDocFilename.classList.remove('text-blue-700');
            currentDocFilename.classList.add('text-amber-700', 'line-through');

            // Add new file info
            const newFileDiv = currentDocInfo.querySelector('.new-file-info');
            if (!newFileDiv) {
              const newFileInfo = document.createElement('p');
              newFileInfo.className = 'text-sm text-amber-900 font-medium mt-1 new-file-info';
              newFileInfo.replaceChildren();
              const arrowIcon = document.createElement('i');
              arrowIcon.className = 'fas fa-arrow-right mr-1';
              newFileInfo.appendChild(arrowIcon);
              newFileInfo.appendChild(document.createTextNode(this.files[0].name));
              currentDocFilename.parentElement.appendChild(newFileInfo);
            } else {
              newFileDiv.replaceChildren();
              const arrowIcon = document.createElement('i');
              arrowIcon.className = 'fas fa-arrow-right mr-1';
              newFileDiv.appendChild(arrowIcon);
              newFileDiv.appendChild(document.createTextNode(this.files[0].name));
            }

            const helpText = currentDocInfo.querySelector('.text-xs.text-blue-600');
            if (helpText) {
              helpText.classList.remove('text-blue-600');
              helpText.classList.add('text-amber-600');
              helpText.textContent = 'The current document will be replaced with the new file when you save.';
            }
          } else {
            // Reset to original state if file is deselected
            resetCurrentDocumentInfoStyle(filename);
          }
        });
        modalFileInput.dataset.changeListenerAttached = 'true';
      }
    }
  }

  // Reset current document info to original style
  function resetCurrentDocumentInfoStyle(filename) {
    const currentDocInfo = document.getElementById('current-document-info');
    const currentDocFilename = document.getElementById('current-document-filename');

    if (currentDocInfo && currentDocFilename) {
      currentDocInfo.classList.remove('bg-amber-50', 'border-amber-300');
      currentDocInfo.classList.add('bg-blue-50', 'border-blue-200');

      const iconEl = currentDocInfo.querySelector('i');
      if (iconEl) {
        iconEl.classList.remove('text-amber-600');
        iconEl.classList.add('text-blue-600');
      }

      const titleEl = currentDocInfo.querySelector('.text-amber-900, .text-blue-900');
      if (titleEl) {
        titleEl.classList.remove('text-amber-900');
        titleEl.classList.add('text-blue-900');
        titleEl.textContent = 'Current Document:';
      }

      currentDocFilename.classList.remove('text-amber-700', 'line-through');
      currentDocFilename.classList.add('text-blue-700');
      currentDocFilename.textContent = filename;

      // Remove new file info
      const newFileInfo = currentDocInfo.querySelector('.new-file-info');
      if (newFileInfo) newFileInfo.remove();

      const helpText = currentDocInfo.querySelector('.text-xs.text-amber-600, .text-xs.text-blue-600');
      if (helpText) {
        helpText.classList.remove('text-amber-600');
        helpText.classList.add('text-blue-600');
        helpText.textContent = 'Leave file selection empty to keep current document, or upload a new file to replace it.';
      }
    }
  }

  // Hide current document info (for upload mode)
  function hideCurrentDocumentInfo() {
    const currentDocInfo = document.getElementById('current-document-info');
    const currentDocFilename = document.getElementById('current-document-filename');

    if (currentDocInfo) {
      currentDocInfo.classList.add('hidden');

      // Reset to original blue styling
      currentDocInfo.classList.remove('bg-amber-50', 'border-amber-300');
      currentDocInfo.classList.add('bg-blue-50', 'border-blue-200');

      const iconEl = currentDocInfo.querySelector('i');
      if (iconEl) {
        iconEl.classList.remove('text-amber-600');
        iconEl.classList.add('text-blue-600');
      }

      const titleEl = currentDocInfo.querySelector('.text-amber-900, .text-blue-900');
      if (titleEl) {
        titleEl.classList.remove('text-amber-900');
        titleEl.classList.add('text-blue-900');
        titleEl.textContent = 'Current Document:';
      }

      if (currentDocFilename) {
        currentDocFilename.classList.remove('text-amber-700', 'line-through');
        currentDocFilename.classList.add('text-blue-700');
      }

      // Remove new file info
      const newFileInfo = currentDocInfo.querySelector('.new-file-info');
      if (newFileInfo) newFileInfo.remove();

      const helpText = currentDocInfo.querySelector('.text-xs');
      if (helpText) {
        helpText.classList.remove('text-amber-600');
        helpText.classList.add('text-blue-600');
      }
    }
  }

  // Helper to show flash messages (uses centralized window.showFlashMessage from flash-messages.js)
  function showFlashMessage(message, type = 'info') {
    if (typeof window.showFlashMessage === 'function') {
      window.showFlashMessage(message, type);
    }
  }

  function createFlashContainer() {
    const container = document.createElement('div');
    container.className = 'flash-messages';
    const form = document.getElementById('focalDataEntryForm');
    if (form) {
      form.parentElement.insertBefore(container, form);
    }
    return container;
  }

  // Helper function to create uploaded document display element
  function createUploadedDocumentElement(doc, fieldId, fieldLabel, fieldConfig) {
    const docContainer = document.createElement('div');
    docContainer.className = 'flex flex-col bg-green-100 border border-green-400 text-green-700 px-4 py-3 rounded relative mb-2';

    // Top row: File info and action buttons
    const topRow = document.createElement('div');
    topRow.className = 'flex items-center justify-between mb-2';

    const leftDiv = document.createElement('div');
    leftDiv.className = 'flex items-center overflow-hidden mr-2 flex-1';

    const icon = document.createElement('i');
    icon.className = 'fas fa-file-alt w-5 h-5 mr-3 flex-shrink-0';

    const infoDiv = document.createElement('div');
    infoDiv.className = 'flex flex-col min-w-0 flex-1';

    // Filename link (will be updated with real document ID after fetch)
    const filenameLink = document.createElement('a');
    filenameLink.className = 'font-semibold hover:underline text-sm truncate';
    filenameLink.textContent = doc.fileName;
    filenameLink.title = doc.fileName;
    filenameLink.href = '#'; // Placeholder, will be updated

    const languageSpan = document.createElement('span');
    languageSpan.className = 'text-xs text-green-600 mt-1';
    languageSpan.textContent = doc.language ? doc.language.toUpperCase() : 'EN';

    infoDiv.appendChild(filenameLink);
    infoDiv.appendChild(languageSpan);
    leftDiv.appendChild(icon);
    leftDiv.appendChild(infoDiv);

    // Action buttons
    const actionsDiv = document.createElement('div');
    actionsDiv.className = 'flex items-center gap-2 flex-shrink-0';

    // Edit button (will be updated with real document ID after fetch)
    const editBtn = document.createElement('button');
    editBtn.type = 'button';
    editBtn.className = 'text-blue-600 hover:text-blue-800 edit-document-btn';
    editBtn.dataset.docId = 'pending'; // Placeholder
    editBtn.dataset.fieldId = fieldId;
    editBtn.dataset.fieldLabel = fieldLabel;
    editBtn.dataset.filename = doc.fileName;
    editBtn.dataset.language = doc.language || 'en';
    editBtn.dataset.documentType = doc.documentType || '';
    editBtn.dataset.year = doc.year || '';
    editBtn.dataset.isPublic = doc.isPublic ? 'true' : 'false';
    if (fieldConfig) {
      editBtn.dataset.fieldConfig = JSON.stringify(fieldConfig);
    }
    editBtn.title = 'Edit Document';
    const editIcon = document.createElement('i');
    editIcon.className = 'fas fa-pen';
    editBtn.appendChild(editIcon);

    // Delete button (will be updated with real document ID after fetch)
    const deleteBtn = document.createElement('button');
    deleteBtn.type = 'button';
    deleteBtn.className = 'text-red-600 hover:text-red-800 delete-document-btn';
    deleteBtn.dataset.docId = 'pending'; // Placeholder
    deleteBtn.title = 'Delete Document';
    const deleteIcon = document.createElement('i');
    deleteIcon.className = 'fas fa-trash-alt';
    deleteBtn.appendChild(deleteIcon);

    actionsDiv.appendChild(editBtn);
    actionsDiv.appendChild(deleteBtn);

    topRow.appendChild(leftDiv);
    topRow.appendChild(actionsDiv);

    // Upload info paragraph (inside the container)
    const infoP = document.createElement('p');
    infoP.className = 'text-xs text-green-600 mt-1 ml-8';
    const now = new Date();
    const dateStr = now.toISOString().split('T')[0];
    infoP.textContent = `(Uploaded just now on ${dateStr})`;

    docContainer.appendChild(topRow);
    docContainer.appendChild(infoP);

    return { container: docContainer, infoP: infoP, editBtn: editBtn, deleteBtn: deleteBtn, filenameLink: filenameLink };
  }

  // Listen for form submission success to convert queued documents to uploaded documents
  document.addEventListener('formSubmitted', (event) => {
    const { action, result } = event.detail || {};

    // Only process successful saves (not submits, as those redirect)
    if (action === 'save' && result && result.success) {
      // Process document deletions - remove documents marked for deletion
      Object.keys(documentsMarkedForDeletion).forEach(docId => {
        const deletionInfo = documentsMarkedForDeletion[docId];
        if (!deletionInfo) return;

        const { element, fieldId } = deletionInfo;

        // Remove the document element and its associated info paragraph
        if (element && element.parentElement) {
          // Remove delete message if present (could be inside or outside the element)
          // NOTE: Keep this logic explicit to avoid accidentally removing siblings (e.g. upload button)
          let deleteMessage = element.querySelector('.delete-message');
          if (!deleteMessage) {
            const maybeSibling = element.nextElementSibling;
            if (maybeSibling && maybeSibling.classList && maybeSibling.classList.contains('delete-message')) {
              deleteMessage = maybeSibling;
            } else {
              deleteMessage = element.parentElement.querySelector('.delete-message');
            }
          }
          if (deleteMessage) deleteMessage.remove();

          // Remove info paragraph (could be inside the element or as a sibling)
          let infoP = element.querySelector('p.text-xs');
          if (!infoP || infoP.parentElement !== element) {
            // Check if it's a sibling
            infoP = element.nextElementSibling;
            if (infoP && !infoP.classList.contains('text-xs')) {
              // Skip delete message, find next sibling
              infoP = infoP.nextElementSibling;
            }
          }
          if (infoP && infoP.classList.contains('text-xs')) {
            infoP.remove();
          }

          // Remove the document element itself
          element.remove();
        }

        // Update field container state
        const fieldContainer = document.querySelector(`[data-field-id="${fieldId}"]`)?.closest('.form-item-block, .bg-gray-50');
        if (fieldContainer) {
          const uploadBtn = fieldContainer.querySelector('.document-upload-btn');
          if (uploadBtn && uploadBtn.parentElement) {
            // Check if there are any more existing documents for this field
            // Only count green documents (red ones are marked for deletion and will be removed)
            const remainingDocs = fieldContainer.querySelectorAll('.bg-green-100.border-green-400').length;

            // Ensure the button's parent is visible first
            uploadBtn.parentElement.style.display = '';

            if (remainingDocs === 0 && (!queuedDocuments[fieldId] || queuedDocuments[fieldId].length === 0)) {
              // No more documents, reset to empty state (shows upload button with dashed border)
              setEmptyState(uploadBtn);
            } else {
              // Still have documents, ensure button shows plus icon
              setHasDocsState(uploadBtn);
            }

            // Check max documents limit and show/hide accordingly
            const maxDocuments = getMaxDocumentsForField(fieldId);
            const currentCount = getCurrentDocumentCount(fieldId);
            if (maxDocuments && currentCount >= maxDocuments) {
              // At or over limit, hide the button
              uploadBtn.parentElement.style.display = 'none';
            } else {
              // Below limit, ensure button is visible
              uploadBtn.parentElement.style.display = '';
            }
          }
        }
      });

      // Clear deletion tracking
      Object.keys(documentsMarkedForDeletion).forEach(key => {
        delete documentsMarkedForDeletion[key];
      });

      // Check if there are any queued documents
      const hasQueuedDocuments = Object.keys(queuedDocuments).some(fieldId =>
        queuedDocuments[fieldId] && queuedDocuments[fieldId].length > 0
      );

      if (hasQueuedDocuments) {
        // Track which fields had queued documents before clearing
        const fieldsWithQueuedDocs = {};

        // Convert queued documents to uploaded document display
        Object.keys(queuedDocuments).forEach(fieldId => {
          // Store the queued docs count before clearing
          if (queuedDocuments[fieldId] && queuedDocuments[fieldId].length > 0) {
            fieldsWithQueuedDocs[fieldId] = queuedDocuments[fieldId].length;
          }
          const queuedDocs = queuedDocuments[fieldId];
          if (!queuedDocs || queuedDocs.length === 0) return;

          const fieldContainer = document.querySelector(`[data-field-id="${fieldId}"]`)?.closest('.form-item-block, .bg-gray-50');
          if (!fieldContainer) return;

          // Get field configuration
          const uploadBtn = fieldContainer.querySelector('.document-upload-btn');
          const fieldLabel = uploadBtn?.dataset.fieldLabel || '';
          let fieldConfig = {};
          try {
            if (uploadBtn?.dataset.fieldConfig) {
              fieldConfig = JSON.parse(uploadBtn.dataset.fieldConfig);
            }
          } catch (e) {
            console.error('Failed to parse field config:', e);
          }

          // Remove queued document containers
          fieldContainer.querySelectorAll('.document-queue-container').forEach(el => el.remove());
          fieldContainer.querySelectorAll('.document-pending-feedback').forEach(el => el.remove());

          // Find where to insert the new documents (before the upload button)
          const uploadBtnParent = uploadBtn?.parentElement;
          if (!uploadBtnParent) return;

          // Check if there's already a documents container
          let docsContainer = fieldContainer.querySelector('.space-y-2.mb-3');
          if (!docsContainer) {
            // Create a container for multiple documents
            docsContainer = document.createElement('div');
            docsContainer.className = 'space-y-2 mb-3';
            uploadBtnParent.parentElement.insertBefore(docsContainer, uploadBtnParent);
          }

          // Convert each queued document to uploaded document display
          queuedDocs.forEach(doc => {
            const { container, infoP, editBtn, deleteBtn, filenameLink } = createUploadedDocumentElement(
              doc, fieldId, fieldLabel, fieldConfig
            );

            // Add to documents container
            docsContainer.appendChild(container);
            docsContainer.appendChild(infoP);
          });

          // Update button state
          if (uploadBtn) {
            setHasDocsState(uploadBtn);
            uploadBtn.dataset.hasExisting = 'true';

            // Update button icon to plus
            const icon = uploadBtn.querySelector('i');
            if (icon) {
              icon.classList.remove('fa-upload');
              icon.classList.add('fa-plus');
            }

            // Show upload button if we're below the limit
            const maxDocuments = getMaxDocumentsForField(fieldId);
            const currentCount = getCurrentDocumentCount(fieldId);
            if (uploadBtn.parentElement && (!maxDocuments || currentCount < maxDocuments)) {
              uploadBtn.parentElement.style.display = '';
            }
          }

          // Clear the queued documents from memory
          queuedDocuments[fieldId] = [];
        });

        // Fetch actual document IDs from server by reloading the form page content
        // This ensures we have the correct document IDs for edit/delete functionality
        setTimeout(() => {
          // Get the form URL
          const form = document.getElementById('focalDataEntryForm');
          if (!form) return;

          const formAction = form.getAttribute('action') || window.location.href;
          const fetchUrl = formAction + (formAction.includes('?') ? '&' : '?') + 'ajax=1';

          const _dufetch = (window.getFetch && window.getFetch()) || fetch;
          _dufetch(fetchUrl, {
            method: 'GET',
            headers: {
              'X-Requested-With': 'XMLHttpRequest'
            }
          })
          .then(response => response.text())
          .then(html => {
            // Parse the HTML to extract document information
            const parser = new DOMParser();
            const doc = parser.parseFromString(html, 'text/html');

            // Update document IDs for all fields that had queued documents
            // Use the fieldsWithQueuedDocs from outer scope (captured in closure)
            Object.keys(fieldsWithQueuedDocs).forEach(fieldId => {
              const queuedCount = fieldsWithQueuedDocs[fieldId];
              const fieldContainer = document.querySelector(`[data-field-id="${fieldId}"]`)?.closest('.form-item-block, .bg-gray-50');
              if (!fieldContainer) return;

              // Find the field in the fetched HTML
              const fetchedFieldContainer = doc.querySelector(`[data-field-id="${fieldId}"]`)?.closest('.form-item-block, .bg-gray-50');
              if (!fetchedFieldContainer) return;

              // Get all documents for this field from fetched HTML
              const fetchedDocs = Array.from(fetchedFieldContainer.querySelectorAll('.bg-green-100.border-green-400'));
              const displayedDocs = Array.from(fieldContainer.querySelectorAll('.bg-green-100.border-green-400'));

              // Match documents by filename - find newly uploaded ones
              if (queuedCount > 0 && displayedDocs.length > 0) {
                // Get the filenames of displayed docs (the ones we just created)
                const displayedFilenames = displayedDocs.map(doc => {
                  const link = doc.querySelector('a');
                  return link ? link.textContent.trim() : null;
                }).filter(f => f);

                // Match each displayed doc with fetched doc by filename
                displayedDocs.forEach((displayedDoc, displayedIndex) => {
                  const displayedFilename = displayedFilenames[displayedIndex];
                  if (!displayedFilename) return;

                  // Find matching fetched doc by filename
                  const fetchedDoc = fetchedDocs.find(fd => {
                    const link = fd.querySelector('a[href*="download_document"]');
                    return link && link.textContent.trim() === displayedFilename;
                  });

                  if (fetchedDoc) {
                    const editBtn = fetchedDoc.querySelector('.edit-document-btn');
                    const deleteBtn = fetchedDoc.querySelector('.delete-document-btn');
                    const filenameLink = fetchedDoc.querySelector('a[href*="download_document"]');

                    if (editBtn && deleteBtn) {
                      const docId = editBtn.dataset.docId;
                      const displayedEditBtn = displayedDoc.querySelector('.edit-document-btn');
                      const displayedDeleteBtn = displayedDoc.querySelector('.delete-document-btn');
                      const displayedFilenameLink = displayedDoc.querySelector('a');

                      if (displayedEditBtn && docId && docId !== 'pending' && !isNaN(parseInt(docId))) {
                        displayedEditBtn.dataset.docId = docId;
                        // Copy all data attributes from fetched button
                        Array.from(editBtn.attributes).forEach(attr => {
                          if (attr.name.startsWith('data-')) {
                            displayedEditBtn.setAttribute(attr.name, attr.value);
                          }
                        });
                      }

                      if (displayedDeleteBtn && docId && docId !== 'pending' && !isNaN(parseInt(docId))) {
                        displayedDeleteBtn.dataset.docId = docId;
                      }

                      if (displayedFilenameLink && filenameLink) {
                        displayedFilenameLink.href = filenameLink.href;
                        displayedFilenameLink.download = filenameLink.download || displayedFilenameLink.download;
                      }

                      // Update the uploaded info text
                      const infoP = displayedDoc.nextElementSibling;
                      if (infoP && infoP.classList.contains('text-xs') && infoP.classList.contains('text-gray-600')) {
                        const fetchedInfoP = fetchedDoc.nextElementSibling;
                        if (fetchedInfoP && fetchedInfoP.textContent) {
                          infoP.textContent = fetchedInfoP.textContent;
                        }
                      }
                    }
                  }
                });
              }
            });
          })
          .catch(error => {
            console.error('Error fetching updated documents:', error);
            // If fetch fails, documents will still appear as uploaded but edit/delete won't work until page reload
            // User can still see them and they'll work properly after a manual page refresh
          });
        }, 500);
      }
    }
  });
}
