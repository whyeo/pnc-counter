% One-time migration/validation tool, never needed by the Python application.
% Run from the repository root: matlab -batch "run('tools/export_matlab_reference.m')"
root = fileparts(fileparts(mfilename('fullpath')));
cd(root);
legacy = fullfile(root, 'legacy', 'matlab');
s = load(fullfile(legacy, 'svm_model.mat'));
model.features = s.svm_features;
model.mean = s.svm_mean;
model.std = s.svm_std;
model.internal_mean = s.svm_model.Mu;
model.internal_std = s.svm_model.Sigma;
model.beta = s.svm_model.Beta;
model.bias = s.svm_model.Bias;
model.classes = s.svm_model.ClassNames;
model.source = 'legacy/matlab/svm_model.mat; MATLAB ClassificationSVM, linear kernel';
rng(42);
X = randn(100, length(s.svm_features)) .* s.svm_std + s.svm_mean;
[pred, scores] = predict(s.svm_model, (X - s.svm_mean) ./ s.svm_std);
validation.validation_x = X;
validation.validation_predictions = pred;
validation.validation_scores = scores;
if ~exist('src/nucleus_analysis/data', 'dir'), mkdir('src/nucleus_analysis/data'); end
fid = fopen('src/nucleus_analysis/data/legacy_svm.json', 'w');
fwrite(fid, jsonencode(model, PrettyPrint=true)); fclose(fid);
if ~exist('tests/fixtures', 'dir'), mkdir('tests/fixtures'); end
fid = fopen('tests/fixtures/legacy_svm_vectors.json', 'w');
fwrite(fid, jsonencode(validation, PrettyPrint=true)); fclose(fid);
if ~exist('validation/local', 'dir'), mkdir('validation/local'); end
addpath(fullfile(legacy, 'common'));
addpath(fullfile(legacy, 'common', 'bfmatlab'));
for file_index = 1:2
    name = sprintf('IMG%d', file_index);
    folder = fullfile(root, 'pnc_counting', 'testfiles', 'testfiles');
    data = nd2read(fullfile(folder, [name '.nd2']));
    ch1 = squeeze(data(:,:,1,:));
    ch2 = max(squeeze(data(:,:,2,:)), [], 3);
    dapi_max = uint8(rescale(double(max(ch1, [], 3))) * 255);
    ch1 = uint8(rescale(double(ch1)) * 255);
    dapi_mean = mean(ch1, 3);
    clear data ch1;
    local_mask = imbinarize(ch2, adaptthresh(ch2, 0.01, ...
        'NeighborhoodSize', 21, 'Statistic', 'gaussian'));
    cache = load(fullfile(folder, [name '_segmentation.mat']));
    masks = cache.masks;
    [~, order] = sort(cellfun(@length, masks.PixelIdxList));
    occupied = false(size(ch2));
    rows = [];
    for j = 1:length(order)
        idx = masks.PixelIdxList{order(j)};
        if nnz(occupied(idx)) > 0.1 * length(idx), continue; end
        mask = false(size(ch2)); mask(idx) = true;
        smooth = imgaussfilt(double(mask), 20) > 0.5;
        props = regionprops(double(mask), 'Circularity', 'Eccentricity', 'Solidity');
        [yy, xx] = ind2sub(size(ch2), idx);
        values = double(dapi_max(idx));
        row = struct('MaskID', length(rows)+1, 'Area', length(idx), ...
            'Smoothness', nnz(mask & smooth) / nnz(mask | smooth), ...
            'Eccentricity', props.Eccentricity, 'Circularity', props.Circularity, ...
            'Solidity', props.Solidity, 'MaxIntensity_IQR', iqr(values), ...
            'MaxIntensity_Mean', mean(values), 'MaxIntensity_Std', std(values), ...
            'CentroidX', mean(xx), 'CentroidY', mean(yy), ...
            'NumberCh2PixelsPositive', nnz(local_mask(idx)));
        rows = [rows; row]; %#ok<AGROW>
        occupied(idx) = true;
    end
    writetable(struct2table(rows), fullfile('validation/local', [name '_matlab.csv']));
    save(fullfile('validation/local', [name '_matlab.mat']), ...
        'dapi_max', 'dapi_mean', 'ch2', 'local_mask', '-v7');
end
disp('SVM and independent MATLAB reference exported.');
