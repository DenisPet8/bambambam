let board = null;
let game = new Chess();
let currentPuzzleId = null;
let puzzleSolved = false;
let pending = false;

$(document).ready(function() {
    board = Chessboard('board', {
        draggable: true,
        position: 'start',
        onDrop: onDrop,
        pieceTheme: 'https://chessboardjs.com/img/chesspieces/wikipedia/{piece}.png'
    });

    // Load initial puzzle with default difficulty (All)
    loadNextPuzzle();
    loadStats();

    // Load new puzzle when difficulty changes
    $('#difficulty-select').change(function() {
        loadNextPuzzle();
    });

    $('#next-btn').click(function() {
        loadNextPuzzle();
    });

    $('#reset-stats-btn').click(function() {
        $.ajax({
            url: '/api/reset-stats',
            method: 'POST',
            success: function() {
                loadStats();
            }
        });
    });
});

function loadNextPuzzle() {
    const diff = $('#difficulty-select').val();
    const url = diff ? `/api/puzzle/next?difficulty=${diff}` : '/api/puzzle/next';

    $.getJSON(url, function(data) {
        currentPuzzleId = data.id;
        game.load(data.fen);
        board.position(data.fen);
        puzzleSolved = false;
        pending = false;
        $('#message').text('').removeClass('correct incorrect');

        // Display current difficulty as a badge
        const diffText = data.difficulty.charAt(0).toUpperCase() + data.difficulty.slice(1);
        $('#current-difficulty').text(diffText)
            .removeClass('easy medium hard')
            .addClass(data.difficulty);
    }).fail(function() {
        alert('Failed to load puzzle. Please try another difficulty.');
    });
}

// ... onDrop and loadStats remain identical to earlier version ...
function onDrop(source, target, piece, newPos, oldPos, orientation) {
    if (puzzleSolved || pending) {
        return 'snapback';
    }

    const move = game.move({
        from: source,
        to: target,
        promotion: 'q'
    });

    if (move === null) return 'snapback';

    pending = true;
    const moveUci = move.from + move.to + (move.promotion || '');

    $.ajax({
        url: '/api/puzzle/check',
        method: 'POST',
        contentType: 'application/json',
        data: JSON.stringify({
            puzzle_id: currentPuzzleId,
            move: moveUci
        }),
        success: function(response) {
            pending = false;
            puzzleSolved = true;
            if (response.correct) {
                $('#message').text('Correct!').addClass('correct').removeClass('incorrect');
            } else {
                $('#message').text('Incorrect. The correct move is ' + response.solution.join(', ')).addClass('incorrect').removeClass('correct');
                game.undo();
                board.position(game.fen());
            }
            loadStats();
        },
        error: function() {
            pending = false;
            game.undo();
            board.position(game.fen());
            alert('Error checking puzzle. Please try again.');
        }
    });
}

function loadStats() {
    $.getJSON('/api/stats', function(data) {
        $('#total').text(data.total_attempts);
        $('#correct').text(data.correct_attempts);
        $('#accuracy').text(data.accuracy);
        $('#streak').text(data.current_streak);
        $('#max-streak').text(data.max_streak);
    });
}