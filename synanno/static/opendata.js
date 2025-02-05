$(document).ready(function () {
  // if data is already stored in the backend enable 'reset' button
  if ($("#resetButton").hasClass("d-inline")) {
    $(".form-control").each(function () {
      $(this).prop("disabled", true);
    });
  } else {
    $(".form-control").each(function () {
      $(this).prop("disabled", false);
    });
  }

  // if data is already stored in the backend enable 'continue' button
  if ($("#continueButton").hasClass("d-inline")) {
    $(".form-control").each(function () {
      $(this).prop("disabled", true);
    });
  } else {
    $(".form-control").each(function () {
      $(this).prop("disabled", false);
    });
  }

  function isFieldEmpty(field) {
    return !field.val() || !field.val().trim();
  }

  function areAllFieldsValid() {
    let allValid = true;
    $("[data-required='true']").each(function () {
      if (isFieldEmpty($(this))) {
        allValid = false;
        return false;
      }
    });
    return allValid;
  }

  function updateSubmitButtonState() {
    $("#processData").prop("disabled", !areAllFieldsValid()).toggleClass("disabled", !areAllFieldsValid());
  }

  function updateFieldColors(accordionItem, userInteraction = false) {
    accordionItem.find("[data-required='true']").each(function () {
      const field = $(this);
      field.css("background-color", userInteraction && isFieldEmpty(field) ? "#fff3cd" : "");
    });
    updateSubmitButtonState();
  }

  function updateHeaderColor(accordionItem) {
    const accordionHeader = accordionItem.find(".accordion-header .accordion-button");
    const anyFieldEmpty = accordionItem.find("[data-required='true']").toArray().some(field => isFieldEmpty($(field)));
    if (accordionItem.hasClass("was-interacted")) {
      accordionHeader.css("background-color", anyFieldEmpty ? "#fff3cd" : "");
    }
  }

  $(".accordion-item").each(function () {
    const accordionItem = $(this);

    accordionItem.on("shown.bs.collapse", function () {
      accordionItem.addClass("was-interacted");
      updateFieldColors(accordionItem, true);
      accordionItem.find(".accordion-header .accordion-button").css("background-color", "");
    });

    accordionItem.on("hidden.bs.collapse", function () {
      accordionItem.addClass("was-interacted");
      updateHeaderColor(accordionItem);
    });

    accordionItem.find("[data-required='true']").on("input change", function () {
      updateFieldColors(accordionItem, true);
    });
  });

  $(".accordion-item").each(function () {
    const accordionItem = $(this);
    updateFieldColors(accordionItem, false);
    updateHeaderColor(accordionItem);
  });

  // toggle between view and neuron centric view
  $('input[type="radio"]').change(function () {
    if ($(this).val() === "view") {
      $("#view-form").show();
      $("#neuron-form").hide();
    } else if ($(this).val() === "neuron") {
      $("#view-form").hide();
      $("#neuron-form").show();
    }
  });

  updateSubmitButtonState();

  // enable the c3 neuron segmentation layer
  function enableC3Layer() {
    fetch('/enable_c3_layer', { method: 'POST' })
        .then(response => response.json())
        .then(data => console.log(data.status))
        .catch(error => console.error('Error enabling c3 layer:', error));
  }

  // disable the c3 neuron segmentation layer
  function disableC3Layer() {
    fetch('/disable_c3_layer', { method: 'POST' })
        .then(response => response.json())
        .then(data => console.log(data.status))
        .catch(error => console.error('Error disabling c3 layer:', error));
  }

  // enable the c3 layer when the modal opens
  $("#neuroglancerModal").on("show.bs.modal", function () {
    fetch('/launch_neuroglancer', { method: 'POST' })
        .then(response => response.json())
        .then(data => {
            $("#neuroglancerIframe").attr("src", data.ng_url);
            fetch('/enable_c3_layer', { method: 'POST' });
        })
        .catch(error => console.error('Error launching Neuroglancer:', error));
  });

  // disable the c3 layer when the modal closes
  $("#neuroglancerModal").on("hidden.bs.modal", function () {
    fetch('/disable_c3_layer', { method: 'POST' });
  });

  document.getElementById('materialization_url').addEventListener('input', function() {
    var materializationUrl = this.value.trim();
    console.log("Materialization URL:", materializationUrl);
    var openNeuronModalBtn = document.getElementById('openNeuronModalBtn');
    if (materializationUrl) {
      openNeuronModalBtn.removeAttribute('disabled');
      fetch('/load_materialization', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ materialization_url: materializationUrl })
        })
        .then(response => response.json())
        .then(data => {
          if (data.status === "success") {
            console.log("Materialization table loaded.");

            // Grab the form values (make sure these IDs match your HTML input fields!)
            var source_url = document.getElementById('source_url').value.trim();
            var target_url = document.getElementById('target_url').value.trim();
            var neuropil_url = document.getElementById('neuropil_url').value.trim();

            // Build the query string with proper URL encoding
            var queryString = '?source_url=' + encodeURIComponent(source_url) +
                              '&target_url=' + encodeURIComponent(target_url) +
                              '&neuropil_url=' + encodeURIComponent(neuropil_url);

            // Use a GET request to fetch the Neuroglancer URL with our form data in tow!
            fetch('/launch_neuroglancer' + queryString, { method: 'GET' })
                .then(response => response.json())
                .then(ngData => {
                    if (ngData.ng_url) {
                        document.getElementById('neuroglancerIframe').src = ngData.ng_url;
                        console.log("Neuroglancer URL set to:", ngData.ng_url);
                    } else {
                        console.error("No Neuroglancer URL received:", ngData.error);
                    }
                })
                .catch(error => {
                    console.error("Error launching Neuroglancer:", error);
                });
          } else {
              console.error("Error loading materialization table:", data.error);
              alert("Invalid materialization table.");
          }
        })
        .catch(error => {
            console.error("Error during fetch:", error);
            alert("Error occurred while loading the materialization table.");
        });
    } else {
      openNeuronModalBtn.setAttribute('disabled', 'disabled');
    }
  });

  $('input[type="radio"][value="neuron"]').change(function () {
    if ($(this).is(':checked')) {
      $("#openNeuronModalBtn").hide();
    }
  });

  $('input[type="radio"][value="view"]').change(function () {
    if ($(this).is(':checked')) {
      $("#openNeuronModalBtn").show();
    }
  });
});
