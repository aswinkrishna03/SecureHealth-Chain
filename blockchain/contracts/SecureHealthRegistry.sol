// SPDX-License-Identifier: MIT
pragma solidity ^0.8.19;

/**
 * @title SecureHealthRegistry
 * @dev Lightweight Ethereum Smart Contract for SecureHealth Chain
 * Handles tamper-evident storage for:
 * 1. Electronic Health Record (EHR) SHA-256 Hashes & Timestamps
 * 2. Federated Learning (FL) Model Updates and Global Aggregated Hashes
 */
contract SecureHealthRegistry {
    address public owner;

    // Struct for storing EHR record metadata
    struct EHRRecord {
        bytes32 recordHash;
        address recordedBy;
        uint256 timestamp;
        bool exists;
    }

    // Struct for storing FL model update contribution
    struct ModelUpdate {
        uint256 roundNumber;
        bytes32 modelHash;
        address nodeAddress;
        uint256 timestamp;
    }

    // Mapping: Record UUID => EHR Record details
    mapping(string => EHRRecord) private ehrRecords;

    // Mapping: Round Number => Array of Model Updates from participating nodes
    mapping(uint256 => ModelUpdate[]) private flRoundUpdates;

    // Mapping: Round Number => Global Aggregated Model Hash
    mapping(uint256 => bytes32) public globalModelHashes;

    // Events
    event EHRRegistered(
        string indexed recordUUID,
        bytes32 indexed recordHash,
        address indexed recordedBy,
        uint256 timestamp
    );

    event ModelUpdateSubmitted(
        uint256 indexed roundNumber,
        bytes32 modelHash,
        address indexed nodeAddress,
        uint256 timestamp
    );

    event GlobalModelPublished(
        uint256 indexed roundNumber,
        bytes32 globalModelHash,
        uint256 timestamp
    );

    modifier onlyOwner() {
        require(msg.sender == owner, "Caller is not the contract owner");
        _;
    }

    constructor() {
        owner = msg.sender;
    }

    // ==========================================
    // MODULE 1, 3 & 4: EHR RECORD HASH STORAGE
    // ==========================================

    /**
     * @dev Registers an EHR record hash on-chain
     * @param _recordUUID Unique identifier of the EHR
     * @param _recordHash SHA-256 hash of the normalized record data
     */
    function registerEHR(string memory _recordUUID, bytes32 _recordHash) public returns (bool) {
        require(!ehrRecords[_recordUUID].exists, "EHR Record already registered on blockchain");
        require(_recordHash != bytes32(0), "Invalid record hash");

        ehrRecords[_recordUUID] = EHRRecord({
            recordHash: _recordHash,
            recordedBy: msg.sender,
            timestamp: block.timestamp,
            exists: true
        });

        emit EHRRegistered(_recordUUID, _recordHash, msg.sender, block.timestamp);
        return true;
    }

    /**
     * @dev Verifies whether an incoming record hash matches the on-chain immutable hash
     * @param _recordUUID Unique identifier of the EHR
     * @param _incomingHash SHA-256 hash re-calculated from current record data
     */
    function verifyEHR(string memory _recordUUID, bytes32 _incomingHash)
        public
        view
        returns (bool isValid, uint256 timestamp, address recordedBy)
    {
        require(ehrRecords[_recordUUID].exists, "Record does not exist on blockchain");
        EHRRecord memory record = ehrRecords[_recordUUID];
        isValid = (record.recordHash == _incomingHash);
        return (isValid, record.timestamp, record.recordedBy);
    }

    /**
     * @dev Fetches registered EHR record details
     */
    function getEHR(string memory _recordUUID)
        public
        view
        returns (bytes32 recordHash, address recordedBy, uint256 timestamp)
    {
        require(ehrRecords[_recordUUID].exists, "Record does not exist");
        EHRRecord memory record = ehrRecords[_recordUUID];
        return (record.recordHash, record.recordedBy, record.timestamp);
    }

    // ==========================================
    // MODULE 2 & 3: FEDERATED LEARNING AUDITING
    // ==========================================

    /**
     * @dev Hospital node logs their local model update hash before aggregation
     */
    function submitModelUpdate(uint256 _round, bytes32 _modelHash) public {
        require(_modelHash != bytes32(0), "Invalid model hash");
        flRoundUpdates[_round].push(
            ModelUpdate({
                roundNumber: _round,
                modelHash: _modelHash,
                nodeAddress: msg.sender,
                timestamp: block.timestamp
            })
        );

        emit ModelUpdateSubmitted(_round, _modelHash, msg.sender, block.timestamp);
    }

    /**
     * @dev FL Coordinator publishes the aggregated global model hash
     */
    function publishGlobalModel(uint256 _round, bytes32 _globalHash) public onlyOwner {
        require(_globalHash != bytes32(0), "Invalid global model hash");
        globalModelHashes[_round] = _globalHash;
        emit GlobalModelPublished(_round, _globalHash, block.timestamp);
    }

    /**
     * @dev Retrieve the count of updates submitted in a specific round
     */
    function getRoundUpdateCount(uint256 _round) public view returns (uint256) {
        return flRoundUpdates[_round].length;
    }
}
