// Document item logic extracted from item-modal.js

export const DocumentItem = {
    setup(modalElement) {
        // Remove existing event listeners to prevent duplicates
        if (modalElement._documentChangeHandler) {
            document.removeEventListener('change', modalElement._documentChangeHandler);
        }

        modalElement._documentChangeHandler = (e) => {
            // Placeholder for future document-specific field handling
        };

        document.addEventListener('change', modalElement._documentChangeHandler);
    },

    teardown(modalElement) {
        if (!modalElement) return;
        if (modalElement._documentChangeHandler) {
            document.removeEventListener('change', modalElement._documentChangeHandler);
            modalElement._documentChangeHandler = null;
        }
    },

    populateForm(modalElement, itemData) {
        // Currently, document fields use shared label/description populated by caller
        // Populate max_documents field from config
        console.log('DocumentItem.populateForm called with itemData:', itemData);

        // Populate optional document type from config
        try {
            const typeSelect = modalElement.querySelector('#item-document-type');
            if (typeSelect) {
                let docType = null;
                if (itemData && itemData.config && itemData.config.document_type) {
                    docType = itemData.config.document_type;
                } else if (itemData && itemData.document_type) {
                    docType = itemData.document_type;
                }
                if (docType && typeof docType === 'string') {
                    typeSelect.value = docType;
                } else {
                    typeSelect.value = '';
                }
            }
        } catch (e) {
            // Non-fatal UI population error
        }

        const maxDocumentsInput = modalElement.querySelector('#item-document-max-documents');
        if (maxDocumentsInput) {
            console.log('Found max documents input field');

            // Try multiple paths to find max_documents value
            let maxDocsValue = null;

            if (itemData.config && itemData.config.max_documents) {
                maxDocsValue = itemData.config.max_documents;
                console.log('Found max_documents in itemData.config:', maxDocsValue);
            } else if (itemData.max_documents) {
                maxDocsValue = itemData.max_documents;
                console.log('Found max_documents directly in itemData:', maxDocsValue);
            }

            if (maxDocsValue) {
                maxDocumentsInput.value = maxDocsValue;
                console.log('Set max documents input value to:', maxDocsValue);
            } else {
                maxDocumentsInput.value = '';
                console.log('No max_documents value found, cleared input');
            }
        } else {
            console.log('Max documents input field not found');
        }

        // Populate display options checkboxes
        const showLanguageCheckbox = modalElement.querySelector('#item-document-show-language');
        const showTypeCheckbox = modalElement.querySelector('#item-document-show-type');
        const showYearCheckbox = modalElement.querySelector('#item-document-show-year');
        const showPublicCheckbox = modalElement.querySelector('#item-document-show-public');

        if (showLanguageCheckbox) {
            showLanguageCheckbox.checked = itemData?.config?.show_language !== false; // Default to true
        }
        if (showTypeCheckbox) {
            showTypeCheckbox.checked = itemData?.config?.show_document_type || false;
        }
        if (showYearCheckbox) {
            showYearCheckbox.checked = itemData?.config?.show_year || false;

            // Show/hide period type options
            const periodTypeOptions = modalElement.querySelector('#period-type-options');
            if (periodTypeOptions) {
                if (showYearCheckbox.checked) {
                    periodTypeOptions.classList.remove('hidden');
                } else {
                    periodTypeOptions.classList.add('hidden');
                }
            }
        }
        if (showPublicCheckbox) {
            showPublicCheckbox.checked = itemData?.config?.show_public_checkbox || false;
        }

        // Populate period type checkboxes
        const singleYearCheckbox = modalElement.querySelector('#item-document-period-single-year');
        const yearRangeCheckbox = modalElement.querySelector('#item-document-period-year-range');
        const monthRangeCheckbox = modalElement.querySelector('#item-document-period-month-range');

        if (singleYearCheckbox) {
            singleYearCheckbox.checked = itemData?.config?.allow_single_year !== false; // Default to true
        }
        if (yearRangeCheckbox) {
            yearRangeCheckbox.checked = itemData?.config?.allow_year_range !== false; // Default to true
        }
        if (monthRangeCheckbox) {
            monthRangeCheckbox.checked = itemData?.config?.allow_month_range !== false; // Default to true
        }
    }
};
