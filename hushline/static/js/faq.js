document.addEventListener('DOMContentLoaded', function() {
    var faqQuestions = document.querySelectorAll('.faq-question');

    faqQuestions.forEach(function(question) {
        question.addEventListener('click', function(e) {
            e.preventDefault();

            var parentLi = this.closest('li');
            var answer = parentLi.querySelector('.faq-answer');
            var arrow = this.querySelector('.arrow'); // Get the arrow span

            // Close currently open answer
            var currentlyOpen = document.querySelector('.faq-answer.active');
            if (currentlyOpen && currentlyOpen !== answer) {
                currentlyOpen.style.display = 'none';
                currentlyOpen.classList.remove('active');
                // Reset the arrow of the previously active question
                var activeQuestion = document.querySelector('.faq-question.active');
                if (activeQuestion) {
                    activeQuestion.classList.remove('active');
                    var activeArrow = activeQuestion.querySelector('.arrow');
                    activeArrow.style.transform = ''; // Reset rotation
                }
            }

            // Toggle current question's answer and arrow
            if (answer.classList.contains('active')) {
                answer.style.display = 'none';
                answer.classList.remove('active');
                this.classList.remove('active'); // Update question active state
                arrow.style.transform = ''; // Reset rotation
            } else {
                answer.style.display = 'block';
                answer.classList.add('active');
                this.classList.add('active'); // Update question active state
                arrow.style.transform = 'rotate(-180deg)'; // Rotate arrow
            }
        });
    });
});
